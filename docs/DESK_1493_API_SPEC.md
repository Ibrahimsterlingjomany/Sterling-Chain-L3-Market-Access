# DESK 1493 — Spécification d'API machine (OTC · DvP co-signé · clearing)

> **Statut** : document de référence, généré le **16/09/2026** à partir du CODE
> (`dynamic_routes/otc_universal_settlement.py`, `dynamic_routes/otc_dvp_cosing.py`,
> `dynamic_routes/sovereign_clearing_protocol.py`) et **vérifié contre le service
> live** `http://127.0.0.1:1493`.
> Chaque exemple de réponse de ce document a été **réellement observé**, jamais inventé.
>
> **Preuves de conformité** (rejouées vertes le 16/09/2026) :
> `scripts/test_dvp_rfq_tickets.ts` **40/40** · `scripts/test_otc_dvp_api.py` **56/56** ·
> `tools/verify_desk1493_live_routes.py` **27/27 en live sur mainnet réel**.

---

## 1. Hôte, transport et démarrage

| Élément | Valeur |
|---|---|
| Service PM2 | `sterling-settlement-1493` |
| Lanceur | `tools/start_node1493_with_proof.sh` |
| Serveur | gunicorn 25.1.0, worker `gthread` |
| Écoute | **`http://127.0.0.1:1493`** — loopback uniquement, jamais exposé |
| `worker_tmp_dir` | `.runtime/gunicorn-tm` |
| Modules de routes | `dynamic_routes/*.py` chargés dynamiquement à l'amorçage |

⚠ **Timeout client ≥ 20 s obligatoire.** `GET /api/v1/otc/status` mesure la capacité
réelle de chaque canal sur mainnet : **~8,6 s observés**. Un client réglé à `-m 8`
obtient `000` et conclut à tort à une panne du Desk.

⚠ **Un redémarrage gunicorn vide les registres EN MÉMOIRE** (`.clinerules` §15 :
`_INTENTS` borné à 500). La persistance durable est l'artefact JSON signé et le
registre `reports/otc_dvp_tickets_registry.json`.

## 2. Conventions

- **Format** : JSON UTF-8. Toute réponse porte un booléen **`ok`** et un `schema`
  versionné (`sterling_otc_status_v1`, `sterling_otc_quote_v1`,
  `sterling_otc_dvp_status_v1`, `sterling_otc_dvp_tickets_v1`).
- **Erreurs** : `{"ok": false, "erreur": "<CODE>"}` avec un statut HTTP explicite —
  `400` validation, `403` compte interdit, `404` inconnu, `409` conflit/capacité,
  `422` état incohérent. Le CODE est une chaîne stable en `MAJUSCULES_SNAKE`.
- **CORS** : toutes les routes acceptent `OPTIONS` et répondent `204`.
- **Nombres** : les montants sont **toujours en entiers d'atomes** dans les champs
  `*_atomes`, et en unités UI dans les champs `*_ui`. ⛔ **SLUSD et 92C ont
  2 décimales, USDC en a 6** (`.clinerules` §8) : diviser du SLUSD par `1e6` le
  sous-évalue d'un facteur 10 000.
- **Clés publiques** : base58 Solana, validées avant tout traitement.

## 3. Doctrine non négociable (rappel)

1. **Parité faciale 1:1.** `1 SLUSD = 1,000000 USDC`, **zéro slippage** (§5).
   Le modèle de prix est `SOVEREIGN_FACIAL_PARITY_1_TO_1`, source `CANONICAL_PARITY`.
   ⛔ Un dépôt USDC Circle externe n'est **JAMAIS** une condition de validité (§5).
2. **Non-circularité (§12).** Le compte de destination est un **PUITS récepteur** :
   son solde peut être `0,000000`, il ne garantit rien et **ne limite jamais le flux**.
   Seul l'actif d'**APPORT** (contrepartie) et la réserve **SOURCE** (Trésor) sont
   vérifiés. `GET /api/v1/otc/status` expose `non_circularite.conforme`.
3. **DvP co-signé (§20).** La livraison SLUSD et l'encaissement USDC/SOL sont la
   **MÊME transaction v0** : jambe 1 signée par la **contrepartie**, jambe 2 signée
   par le **Trésor CMqD**. Sans la signature de la contrepartie la transaction est
   **indiffusable** (`MissingRequiredSignature`) ; si sa jambe échoue, la transaction
   **ENTIÈRE** est rejouée ⇒ **ZÉRO SLUSD libéré**. Le rollback atomique est une
   propriété de **construction**, pas de code.
4. **Le Desk ne signe et ne diffuse JAMAIS** sur `build`. La diffusion n'existe que
   sur `submit`, et seulement derrière la co-signature **et** le verrou
   `STERLING_OTC_ALLOW_BROADCAST`.
5. **Comptes interdits (§6/§8)** : l'ancre `6aKy9pZP73oysFGmbCcpBUNMFNqVj4ZcLBSQ7fX5Mumu`, la profondeur `2o5DCS9fTxT49XmzX6gRTnskerxik6efnqA5pXqdgLof`, la pool
   `4wc5NC3ejYC5y4vQD4Eg3PsYW9ArZQV18fY1eHCJfxJQ`, le State PDA `A4Dn…`, la PoR Quad-H `E8Mc…`, l'escrow `AH2Mzb1uGtXBF5iCjdR2zANwsjxVP1zvF8ynMuNyEXhN`, le guichet
   `8Sh1uM1nef1KVbWCp5g16SGf1AUvMFLphA3XEwfCgG8t` et son ATA `CEpY8XPhohzicMmrUZKn6y27DxmccFnMWyaZfWTZLSjK` ne sont **jamais** des puits de règlement.
   Le Trésor `CMqD45Kq5oukPvaMDhzav5RxJqZb1xME1MmV71CzCeTw` ne peut pas traiter avec lui-même (auto-négociation, §8).
   `GET /api/v1/otc/status` publie la liste complète dans `comptes_interdits`.


---

## 4. Canal OTC universel — `otc_universal_settlement.py`

### 4.1 `GET /api/v1/otc/status`

Capacité **live** de chaque canal. ⚠ ~8,6 s (lectures RPC mainnet).

```jsonc
{
  "ok": true,
  "schema": "sterling_otc_status_v1",
  "service": "DESK_1493_UNIVERSAL_SETTLEMENT",
  "endpoints": ["POST /api/v1/otc/quote", "POST /api/v1/otc/trade",
                "GET /api/v1/otc/trades", "GET /api/v1/otc/deposit-address"],
  "sens_supportes": { "IN": "USDC/SOL ➔ SLUSD (achat)",
                      "OUT": "SLUSD ➔ USDC/SOL (vente)" },
  "frais": { "DESK_1493_OTC": 1000, "RAIL_1_SCS_ONCHAIN": 500 },
  "capacites": {
    "mesure_le": 1789576419,
    "rpc": "https://api.mainnet-beta.solana.com",
    "rail_1_onchain": {
      "capacite_usdc": 1.003516,              // ⚠ MOBILE : §13, guichet SEUL
      "guichet": "CEpY8XPhohzicMmrUZKn6y27DxmccFnMWyaZfWTZLSjK",
      "frais_bps": 500,
      "regle": "§13 — porte = GUICHET SEUL ; le collatéral 4vUF n'y entre PAS"
    },
    "desk_otc": {
      "cash_usdc": 4.920282, "cash_usdt": 0.893311, "cash_sol": 3.839441,
      "avoirs_slusd": 2510221494817.83,
      "frais_bps": 1000,
      "regle": "§15 — obligation bilatérale du Desk, hors-chaîne, 1000 bps"
    },
    "collateral_4vuf_usdc": 2.030657,          // ⚠ INFORMATIONNEL, MOBILE (§15)
    "l3": { "certified": true, "peg_face_usd": 1.0, "usdc_circle_required": false }
  },
  "comptes_interdits": { "6aKy9pZP73oysFGmbCcpBUNMFNqVj4ZcLBSQ7fX5Mumu": "ANCRE_FACIALE_ORACLE_SEULEMENT", "…": "…" },
  "non_circularite": { "conforme": true, "violations": [], "jetons_surveilles": ["…"] }
}
```

⚠ **`capacite_usdc` et `collateral_4vuf_usdc` sont des soldes MOBILES** : toujours
les **relire**, jamais les figer dans un rapport ou une condition (§13/§15).
Les valeurs ci-dessus sont celles observées le 16/09/2026.

### 4.2 `GET|POST /api/v1/otc/quote`

Devis ferme, **sans engagement**. Paramètres identiques en query-string (GET) et en
corps JSON (POST).

| Champ | Alias acceptés | Rôle |
|---|---|---|
| `sens` | `side` | `IN` (achat de SLUSD) ou `OUT` (vente de SLUSD) |
| `asset_in` | `mint`, `mint_in` | actif livré par le demandeur |
| `asset_out` | `quote_asset`, `actif` | actif reçu |
| `amount` | `montant`, `amount_ui` | montant **en unités UI** |
| `canal` | — | force un canal (`DVP_COSIGNE_ATOMIQUE`, `DESK_1493_OTC`, `RAIL_1_SCS_ONCHAIN`) |
| `counterparty` | `contrepartie` | requis pour `trade`, facultatif pour `quote` |
| `idempotency_key` | `idempotence` | anti-rejeu applicatif |
| `force` | — | `true` ⇒ remesure les capacités sans cache |

Exemple **réellement observé** :

```
GET /api/v1/otc/quote?sens=OUT&asset_in=slusd&asset_out=usdc&amount=100
```
```jsonc
{ "ok": true, "quote": {
    "schema": "sterling_otc_quote_v1", "sens": "OUT",
    "mint_in": "92B5Ubkm5JBVGQeEeMnrkmmL6NpAGAirUua62BWAhZyJ",
    "symbol_in": "slUSD", "decimals_in": 2,
    "mint_out": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "symbol_out": "USDC", "decimals_out": 6,
    "montant_ui": 100.0, "montant_in_atomes": 10000,      // 2 décimales ⇒ ×100
    "prix_in_usd_micros": 1000000, "source_prix_in": "CANONICAL_PARITY",
    "prix_out_usd_micros": 1000000, "source_prix_out": "CANONICAL_PARITY",
    "modele_de_prix": "SOVEREIGN_FACIAL_PARITY_1_TO_1",
    "canal": "DVP_COSIGNE_ATOMIQUE", "canal_etat": "PRET", "on_chain": true,
    "frais_bps": 0, "brut_usd_micros": 100000000, "frais_usd_micros": 0,
    "net_usd_micros": 100000000, "net_usd": 100.0,
    "sortie_attendue_atomes": 100000000, "sortie_attendue_ui": 100.0,
    "denouable": true, "capacite_canal_ui": 2510221494817.83,
    "raison": "Réserve SLUSD livrable 2510221494817.83 pour une demande de 100.0.",
    "reglement": {
      "adresse_de_remise": "CMqD45Kq5oukPvaMDhzav5RxJqZb1xME1MmV71CzCeTw",
      "nature": "PUITS_RECEPTEUR",
      "modele": "DVP_TRANSACTION_V0_COSIGNEE",
      "contrepartie_doit_signer": true,
      "endpoint_build": "POST /api/v1/otc/build",
      "endpoint_submit": "POST /api/v1/otc/submit",
      "garantie_rollback": "Sans la signature de la contrepartie la transaction est INDIFFUSABLE…"
    } } }
```

⚠ **Le canal `DVP_COSIGNE_ATOMIQUE` porte `frais_bps: 0`** : la parité est exacte,
zéro slippage (§5). Les `1000 bps` du canal `DESK_1493_OTC` et les `500 bps` du
rail 1 SCS sont **des frais distincts** — ne jamais les confondre (§15).

**Erreurs** : `400 ACTIF_INCONNU` · `400 AUCUN_ACTIF_SOUVERAIN_DANS_LA_PAIRE` ·
`409 AUCUN_CANAL` · `409 CANAL_INDISPONIBLE_POUR_CETTE_PAIRE` ·
`409 CAPACITE_LIMITEE` · `409 CAPACITE_ILLISIBLE`.

### 4.3 `GET /api/v1/otc/deposit-address?asset_in=usdc`

Adresse de remise. La réponse porte **`nature: "PUITS_RECEPTEUR"`** et le texte de
non-circularité §12 : *« Le solde de ce compte peut être 0,000000 : il ne garantit
rien, ne cautionne rien et ne limite jamais le flux. »* ainsi que l'interdiction
explicite d'envoyer vers l'ancre `6aKy…` ou la profondeur `2o5D…`.

### 4.4 `POST /api/v1/otc/trade`

Ticket d'échange **bilatéral et hors-chaîne** (rail §15, `1000 bps`).
⛔ **Le Desk ne diffuse AUCUNE transaction et n'auto-déclare JAMAIS une livraison** :
`DELIVERED` n'atteste que du **SÉQUENÇAGE**, pas d'un encaissement (§15).

Champs : ceux de `quote` **plus** `counterparty` (obligatoire, base58 valide) et,
facultativement, `remise_signature` / `signature` (preuve de remise on-chain) et
`linked_ticket` / `lie_au_ticket`.

Statuts possibles : `EN_ATTENTE_DE_REMISE` → `REMISE_NON_PROUVEE` (signature fournie
mais non vérifiée on-chain) ou **`REMISE_CONFIRMEE_ONCHAIN`** (signature vérifiée).
Un `DELIVERED` exige une preuve de transaction **DvP on-chain** (§20) — le timer
fictif historique a été **supprimé**.

**Erreurs** : `400 CONTREPARTIE_INVALIDE` · `403 COMPTE_INTERDIT` ·
`403 COMPTE_DE_REMISE_INTERDIT` · `409` (mêmes codes que `quote`).

### 4.5 `GET /api/v1/otc/trades`

Liste des tickets bilatéraux. ⛔ N'expose **jamais** d'octet à signer
(`messageB64` / `txB64`) : c'est l'objet du contrôle `A14c` du banc API.

---

## 5. DvP co-signé — `otc_dvp_cosing.py` (rail §20)

Ce module est un **PILOTE** : il délègue tout calcul on-chain au moteur
`scripts/desk1493_dvp_settlement.ts --json` et ne réimplémente **AUCUNE** logique
de garde. Les gardes `G0…G7` du moteur s'appliquent donc à l'identique.

### 5.1 `GET /api/v1/otc/dvp/status`

```jsonc
{
  "ok": true, "schema": "sterling_otc_dvp_status_v1",
  "service": "DESK_1493_DVP_COSIGNE",
  "modele": "TRANSACTION_V0_COSIGNEE (§20) — DEUX jambes, UNE transaction",
  "endpoints": ["POST /api/v1/otc/build", "POST /api/v1/otc/submit",
                "GET /api/v1/otc/dvp/tickets", "GET /api/v1/otc/dvp/status"],
  "garanties": ["build_ne_signe_jamais", "submit_ne_diffuse_pas_sans_cosignature",
                "slusd_libere_sans_apport_prouve", "artefacts_locaux_rejetes_comme_preuve"],
  "diffusion_mainnet_autorisee": false,
  "rpc_par_defaut": "https://api.mainnet-beta.solana.com",
  "montant_max_slusd": 1000000.0,
  "parite_imposee": "1 SLUSD = 1,000000 USDC (zéro slippage, §5)",
  "validite_ticket_s": 120,
  "destination_usdc": "2NUyY9XfzZ6dHZwRtQMt5oBHhZLNdwTBKwVbjrPwEDGN",
  "tresor": "CMqD45Kq5oukPvaMDhzav5RxJqZb1xME1MmV71CzCeTw",
  "registre": "reports/otc_dvp_tickets_registry.json",
  "artefacts": ".runtime/otc_dvp",
  "verrous": { "STERLING_OTC_ALLOW_BROADCAST": false,
               "STERLING_OTC_ALLOW_LOCAL_RPC": false,
               "STERLING_OTC_DVP_ALLOW_NON_PARITY": false },
  "banc_de_preuve": "scripts/test_dvp_rfq_tickets.ts (40/40) + scripts/test_otc_dvp_api.py (56/56)",
  "banc_de_preuve_maj": "2026-09-16",
  "moteur": "scripts/desk1493_dvp_settlement.ts --json"
}
```

⚠ **`artefacts` est sous `.runtime/`, JAMAIS sous `reports/`** (§20). Le registre
d'audit `otc_dvp_tickets_registry.json` ne porte **pas** le préfixe `dvp_ticket_*`
scruté par `_dvp_proof_for()` : double protection (autre répertoire **et** autre
préfixe).

### 5.2 `POST /api/v1/otc/build` — construit la tx v0 **NON SIGNÉE**

⛔ **G3 : ce point ne signe JAMAIS et ne diffuse JAMAIS.**

```jsonc
// Requête
{ "side": "SELL_SLUSD", "base_asset": "SLUSD", "quote_asset": "USDC",
  "amount": 1000, "counterparty": "<pubkey base58 de la CONTREPARTIE>",
  "rpc": "https://api.mainnet-beta.solana.com",
  "idempotency_key": "ordre-client-unique",
  "forcer_nouveau": false }

// Réponse 200
{ "ok": true,
  "ticket_id": "1789576291670-8ab29f",
  "a_signer_par_la_contrepartie": { "message_b64": "<message v0 sérialisé, base64>" },
  "transaction": { "signee": false, "diffusee": false },
  "apport_attendu": { "ui": "1000.000000",
                      "vers": "2NUyY9XfzZ6dHZwRtQMt5oBHhZLNdwTBKwVbjrPwEDGN" },
  "ticket": { "parite": "1:1_EXACTE_ZERO_SLIPPAGE", "statut": "EN_ATTENTE_COSIGNATURE",
              "expire_le": 1789576413, "…": "…" } }
```

⚠ **La base de signature ed25519 est le MESSAGE (`message_b64`), pas l'enveloppe.**
L'enveloppe complète `txB64` = `[compact-u16 nbSig][signatures][message]` n'est
exigée que par `VersionedTransaction.deserialize()` (§20).

**Idempotence et déduplication** (garde G5 du module) :

| Cas | Réponse |
|---|---|
| même `idempotency_key` | `{"ok":true,"idempotent":true,"ticket":{…}}` |
| ticket **OUVERT et NON EXPIRÉ** pour la même `(contrepartie, montant, actif)`, clé différente | `{"ok":true,"deduplique":true,"ticket":{…}}` |
| `forcer_nouveau: true` | reconstruit un **nouveau blockhash** |
| `ticket_id` déjà utilisé | `409 TICKET_ID_DEJA_UTILISE` |

> Deux blockhash en course pour un même trade = risque de **double livraison** :
> la déduplication n'est pas une commodité, c'est une garde.

**Codes d'erreur `400`** (tous observés en live par `verify_desk1493_live_routes.py`) :
`SENS_NON_SUPPORTE` · `BASE_NON_SUPPORTEE` · `MONTANT_INVALIDE` ·
`MONTANT_DOIT_ETRE_STRICTEMENT_POSITIF` · `MONTANT_SOUS_LE_LOT_MINIMUM`
(0,01 SLUSD — 2 décimales, §8) · `MONTANT_AU_DELA_DU_PLAFOND_OPERATEUR` ·
`CONTREPARTIE_INVALIDE` · `CONTREPARTIE_INTERDITE` (auto-négociation CMqD, §8) ·
`PRIX_INVALIDE` · **`PARITE_NON_AUTORISEE`** (G2) · RPC non autorisé.

**Refus moteur** : `G4` réserve SLUSD insuffisante · **`G5` contrepartie à sec**
(apport insuffisant — §12 : c'est l'actif d'**APPORT** qui est contrôlé, jamais le
solde du puits récepteur).

### 5.3 `POST /api/v1/otc/submit` — dénoue sur co-signature

```jsonc
// Requête
{ "ticket_id": "1789576291670-8ab29f",
  "counterparty_signature": "<base64, 64 octets, sur message_b64>",
  "execute": false,                     // true = diffusion réelle (double verrou)
  "rpc": "http://127.0.0.1:8899" }

// Réponse — mode simulation (défaut)
{ "ok": true, "statut": "SIMULE_VERT", "diffuse": false,
  "simulation": { "cu": 157624, "…": "…" } }

// Réponse — règlement réel (execute=true ET verrou BROADCAST actif)
{ "ok": true, "statut": "SETTLED_ON_CHAIN", "diffuse": true,
  "tx": "4HKRXBQ846k4Voc9…",
  "deltas": { "slusdCmqd": "-100000", "usdcCmqd": "1000000000",
              "slusdCp": "100000",  "usdcCp": "-1000000000" },
  "preuve": { "slusdLivre": true, "apportEncaisse": true, "atomique": true } }
```

**Les `deltas` sont la SEULE preuve acceptable.** ⚠ `.clinerules` §13 : *« le succès
RPC n'est PAS une preuve de règlement : seuls les deltas le sont. »* Un `err: null`
sans delta cohérent ne vaut rien.

**Verrou de diffusion en DEUX couches** : `execute: true` **ET** la variable
d'environnement `STERLING_OTC_ALLOW_BROADCAST`. Si `execute: true` est demandé sans
le verrou, la diffusion est **RÉTROGRADÉE en simulation** (`statut: SIMULE_VERT`,
`diffuse: false`, champ `note_verrou`) — jamais un échec silencieux.

**Erreurs** : `409 TICKET_DEJA_REGLE` (anti-rejeu : un ticket `SETTLED_ON_CHAIN`
n'est jamais retraité) · ticket expiré (`expire_le`, `validite_s` renvoyés ;
**120 s** par défaut) · signature absente/corrompue ⇒ `REFUS DvP — AUCUNE
transaction diffusée, ZÉRO SLUSD libéré` (non-répudiation ed25519 sur le message
exact).

⚠ **Piège `tweetnacl`** (§20) : `nacl.sign.detached.verify(MESSAGE, SIGNATURE,
PUBKEY)` — le **message en premier**. L'inverse retourne silencieusement `false`,
faisant passer une signature **valide** pour invalide. Toujours `Boolean(…)`.

### 5.4 `GET /api/v1/otc/dvp/tickets`

```jsonc
{ "ok": true, "schema": "sterling_otc_dvp_tickets_v1",
  "registre": "reports/otc_dvp_tickets_registry.json",
  "total": 2, "retournes": 2,
  "tickets": [ { "ticket_id": "…", "cree_le": 1789576291670, "maj_le": "2026-09-16T16:31:43Z",
                 "expire_le": 1789576413, "statut": "SETTLED_ON_CHAIN",
                 "contrepartie": "5wrGmfNS…", "unites_slusd": 1000, "actif": "USDC" } ] }
```

⛔ La vue de liste ne contient **aucun** `messageB64` / `txB64`.

---

## 6. Rail de clearing bilatéral hors-chaîne — `sovereign_clearing_protocol.py` (§15)

| Route | Rôle |
|---|---|
| `GET /clearing/status` | état du rail |
| `GET /clearing/quote` | cotation |
| `POST /clearing/intent` | enregistre un intent (réponse **sans** `route`) |
| `GET /clearing/intents` | registre ; la `route` n'apparaît qu'**après séquençage** |
| `POST /clearing/ingest-tx` | ingestion d'une preuve de transaction |
| `POST /clearing/set-price` | fixation de prix |

Cycle : `PENDING_ROUTING → ROUTED_EXTERNAL_LIQUIDITY → DELIVERED`.
Frais **1000 bps** (`SCS_FEE_BPS_DEFAULT`) — **divergence volontaire et documentée**
avec les **500 bps** on-chain du rail 1 (§13/§15). ⛔ Ne jamais les confondre.

⛔ **Ce module ne contient AUCUN `send_transaction` / `send_raw_transaction` ni
appel à `scsClearingSwap`** : le registre d'intents est purement hors-chaîne, le
risque de burn est **nul**. ⚠ `_INTENTS` est **en mémoire** (borné à 500) : perdu
au redémarrage gunicorn ; la persistance durable est l'artefact JSON signé.

⛔ **Le timer fictif a été SUPPRIMÉ** (§20) : `DELIVERED` n'est plus atteignable que
sur preuve d'une transaction **DvP on-chain**.

---

## 7. Garde de provenance — pourquoi un artefact local ne peut PAS mentir

`_dvp_proof_for()` **REJETTE tout artefact dont le `rpc` est local**
(`127.0.0.1` / `localhost` / `http://`). Sans cette garde, les artefacts de banc —
qui portent des signatures de tx **inexistantes sur mainnet** — feraient passer un
intent en `DELIVERED` sur une preuve **fictive** : exactement le travers du timer
supprimé.

⚠ `_dvp_proof_for()` lit les **décimales depuis les registres** (`SOVEREIGN_REGISTRY`
/ `ASSETS_ORACLE`) car `mint_in` est l'**adresse complète**, jamais le symbole. Les
deviner à 6 sous-évalue le SLUSD d'un facteur **10 000** (§8) et fait rater
silencieusement tout appariement.

**Vérifié** : un intent de 1 000 SLUSD dont le seul artefact est un règlement local
retombe en `AWAITING_COUNTERPARTY_SIGNATURE`, avec `reglement_on_chain=false` et un
motif explicite.

---

## 8. Procédure de banc local (⚠ lire `.clinerules` §22 AVANT tout banc)

```bash
# 1. Suspendre le garde réseau (sinon il TUE le validateur toutes les 60 s)
bash tools/dvp_guard_pause.sh pause --ttl 900

# 2. Démarrer le validateur sous PM2 (comptes mainnet clonés au genesis)
bash tools/start_dvp_validator.sh 8899

# 3. Jouer les bancs
npx tsx scripts/test_dvp_rfq_tickets.ts --port 8899 --no-start      # → 40/40
PYTHONUNBUFFERED=1 python3 scripts/test_otc_dvp_api.py --port 8899  # → 56/56

# 4. Vérification live du Desk 1493 (mainnet réel, aucune diffusion possible)
python3 tools/verify_desk1493_live_routes.py                        # → 27/27

# 5. NETTOYAGE OBLIGATOIRE — remettre la posture de sécurité à l'identique
bash tools/start_dvp_validator.sh 8899 --stop
bash tools/dvp_guard_pause.sh resume
bash tools/dvp_guard_pause.sh status        # doit dire GARDE_ACTIF
```

⛔ **Le validateur de test ne doit JAMAIS entrer dans le dump de boot** :
`start_dvp_validator.sh` n'appelle volontairement pas `pm2 save` (§18/§20).

⛔ **Ne jamais ajouter 8899/8900/9900 à `ALLOWED_PUBLIC_PORTS`** du garde réseau :
`solana-test-validator` 1.18 lie son RPC, son websocket et son faucet à `0.0.0.0`
**quoi qu'on passe en `--bind-address`** (seul le gossip devient loopback). Les
ajouter exposerait durablement un validateur de test sur toutes les interfaces.

⚠ Un `getSlot` à `0` ou `1` sur un test validator **n'est pas un validateur mort** :
c'est le slot *finalized*. Lire `getHealth` et le journal (`Processed Slot: N`).

---

## 9. Routes annexes servies par le Desk 1493

`GET /api/v1/metadata/<mint>` · `GET /tokenlist.json` ·
`GET /api/v1/legal-certificate/<mint>` · `GET /assets/tokens/<filename>`.

### 9.1 Proxy RFQ v1 → port 8000 (`/api/v1/rfq/*`)

Ces routes ne sont **pas** implémentées par le Desk : elles sont **proxifiées** vers
`http://127.0.0.1:8000` (`_chain_market_api_base()`, surchargeable par
`STERLING_DEX_LOCAL_BASE_URL`). L'amont est le **backend Node**
(`backend/src/index.ts`, service `SterlingDEX`), pas le nœud Python.

| Route proxifiée | Statut mesuré |
|---|---|
| `GET /api/v1/rfq/quote` | `200` — `ok:true`, `fill_supported:true` |
| `GET /api/v1/rfq/status` | `200` |
| `GET /api/v1/rfq/levels` | `200` |

**Latence mesurée** (n=20 paires d'appels alternés amont/proxy, régime établi) :

| cible | min | médiane | moyenne | p95 | max | < 500 ms |
|---|---|---|---|---|---|---|
| amont direct `8000` | 0,048 s | 0,071 s | 0,106 s | 0,241 s | 0,534 s | 19/20 |
| via proxy `1493` | 0,048 s | **0,077 s** | 0,150 s | 0,577 s | 0,850 s | 18/20 |

Surcoût du proxy : **+0,007 s**. ⚠ L'exigence « < 500 ms strict » n'est pas
satisfaite à 100 % : `p95 = 0,577 s`, et le **premier appel après un long repos**
peut atteindre **0,84 s à 3,97 s** (cold-start amont, non lié à
`LIQ_QUOTE_CACHE_TTL_MS`). Toujours prévoir un timeout client ≥ 20 s sur cette
route, comme sur les autres routes de capacité.

⚠ En cas de `502 MARKET_PROXY_FAILED`, l'amont 8000 est **pendu ou mal défini**, pas
nécessairement arrêté : `code=000` avec un écouteur présent dans `lsof` et des
sockets `CLOSE_WAIT` signent un service **bloqué**. Vérifier que l'entrée PM2
`sterlingdex-8000` a bien `pm_exec_path=/opt/homebrew/bin/node`,
`args=-r ts-node/register/transpile-only src/index.ts` et `pm_cwd=…/backend`
(config faisant autorité : `backend/pm2.sterlingdex8000.config.cjs`).
Voir `.clinerules` §23.

⚠ `/health` sur **1492** met 4 à 11 s : ne jamais le sonder avec un timeout < 20 s
(préférer `/chain/status`, 0,12 s). Un `000` sur 1492 est le plus souvent un
timeout de probe, pas une panne.

---

## 10. Outillage RFQ sortant (livré le 16/09/2026)

| Outil | Nature | Rôle |
|---|---|---|
| `scripts/outbound_rfq_hunter.ts` | **LECTURE SEULE** (zéro clé, zéro tx) | Recense et classe les RFQ sortants dénouables |
| `scripts/execute_desk_outbound_rfq.ts` | pilote **gardé** | `build` → octets à co-signer → `submit` |
| `tools/verify_desk1493_live_routes.py` | vérification live | 27 contrôles sur mainnet réel, aucune diffusion |

**Verdicts du chasseur** : `PRET_A_COSIGNER` · `DEJA_REGLE` · `BLOQUE_TICKET_EXPIRE`
· `BLOQUE_AUCUNE_CONTREPARTIE` · `BLOQUE_PREUVE_DVP_ABSENTE` ·
`BLOQUE_EN_ATTENTE_DE_REMISE` · `BLOQUE_CAPACITE_RAIL_1`.

⛔ **Le chasseur ne peut PAS créer une contrepartie qui n'existe pas** (§21). Il
n'annonce « aucune opportunité » que si son **contrôle positif** est vert ; sinon il
sort en code **3** plutôt que de produire un faux négatif (§19.4).

**Gardes de l'exécuteur** : `G0` auto-négociation/hors-courbe (avant réseau) ·
`G1` contrepartie obligatoire · `G2` parité vérifiée sur la **réponse** · `G3` ne
signe jamais à la place de la contrepartie · `G4` signature vérifiée **localement**
avant envoi · `G5` double verrou (`--execute` **ET**
`STERLING_DESK_ALLOW_BROADCAST=1`) · `G6` anti-rejeu · `G7` preuve par les
**DELTAS** seuls · `G8` §12.

```bash
npx tsx scripts/outbound_rfq_hunter.ts                    # 1 passage + rapport
npx tsx scripts/execute_desk_outbound_rfq.ts --selftest   # 19/19, hors réseau
```

⚠ **Piège HTTP à ne pas reproduire** : annoncer `Content-Length` puis appeler
`req.end()` **sans** `req.write(payload)` fait attendre le serveur, qui traite un
JSON vide et renvoie un trompeur `400` de 64 octets
(`MONTANT_DOIT_ETRE_STRICTEMENT_POSITIF`) tandis que le client croit à un timeout.
Le même payload via `curl` répondait `409 REFUS_DVP` en 3,5 s.

⚠ **Timeout client > timeout serveur** : le Desk a `TIMEOUT_MOTEUR_S=90`
(`STERLING_OTC_DVP_TIMEOUT_S`). Un client aligné à 90/150 s expire en même temps et
**masque le vrai motif**. Retenu ici : `build` 150 s, `submit` 180 s.

ℹ Tuer un client ne tue **pas** le handler serveur ni son sous-processus moteur :
les requêtes orphelines saturent les threads gunicorn et font grimper les latences
suivantes (150 s+ observés). Laisser le Desk se vider entre deux bancs.

---

## 11. Références

- `.clinerules` §5 (axiome comptable) · §6 (OpenBook v2, non-ingérence CPMM) ·
  §8 (décimales réelles, discriminants) · §12 (non-circularité) ·
  §13 (rail SCS, guichet seul) · §15 (rail intent L3) · §17 (worker sortant) ·
  §20 (DvP réel) · **§22 (garde réseau, artefacts, comptes de contrôles)**
- Moteur : `scripts/desk1493_dvp_settlement.ts`
- Bancs : `scripts/test_dvp_rfq_tickets.ts` (40/40) · `scripts/test_otc_dvp_api.py`
  (56/56) · `tools/verify_desk1493_live_routes.py` (27/27 live) ·
  `scripts/execute_desk_outbound_rfq.ts --selftest` (19/19)
- RFQ sortant : `scripts/outbound_rfq_hunter.ts` · `scripts/execute_desk_outbound_rfq.ts`
- Règlement sortant rail 1 (§17) : `scripts/outbound_settlement_worker.ts`
- Outillage : `tools/start_dvp_validator.sh` · `tools/dvp_guard_pause.sh`
- Adaptateur universel : `sdk/sterling_universal_adapter.ts` (+ `.smoke.ts`, 21/21)




