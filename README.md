# STERLING CHAIN L3 — Infrastructure d'accès au marché pour Market Makers & Desks OTC

**Émetteur** : Sterling Ibrahim Jomany, opérateur souverain de la Sterling Chain L3.
**Actifs** : SLUSD (stable souverain L3) · 92C — carnets **OpenBook v2** sur Solana mainnet.
**Surface publique** : REST + WebSocket + SDK (TypeScript, Python) + OpenAPI 3.0 + Postman.

---

## Pourquoi trader nos RFQ

1. **Décote contractuelle de 150 bps** sur chaque ticket FRQ (grille multi-coupures
   50 → 10 000 SLUSD, timeout 75 slots) : votre quote_required = 98,5 % du nominal.
2. **Règlement DvP ATOMIQUE par construction** : une seule transaction Solana v0 porte
   votre paiement (USDC/SOL → trésorerie `CMqD45Kq5oukPvaMDhzav5RxJqZb1xME1MmV71CzCeTw`) ET notre livraison (SLUSD → votre ATA).
   Sans votre co-signature ed25519 la transaction est **indiffusable** ; si votre jambe
   échoue, la transaction ENTIÈRE est rejouée. **Zéro risque de règlement manqué dans
   les deux sens** — ce n'est pas une promesse, c'est une propriété de la transaction.
3. **Onboarding en < 5 minutes, sans KYC préalable** : handshake ed25519
   challenge-réponse → jeton Bearer (TTL 7 jours). Votre clé Solana standard suffit.
4. **Market data publique temps réel** : BBO, profondeur L2, klines 1m, traces de
   fills — REST (60 r/m) + push WebSocket — directement depuis les carnets mainnet.
5. **Transparence radicale** : chaque réponse embarque ses limites honnêtes
   (`volume_24h=null` tant qu'aucune contrepartie externe n'est mesurée, attribution
   de profondeur au Desk, motifs de refus explicites `REFUS_DVP`).

## Chiffres réels (mesurés on-chain le 22/09/2026 — relire, jamais figer)

| grandeur | valeur | source |
|---|---|---|
| Spread facial ancre SLUSD/USDC | bid 0,9999 / ask 1,0000 (**1,0 bp**) | carnet `6aKy9pZP73oysFGmbCcpBUNMFNqVj4ZcLBSQ7fX5Mumu` via `/api/v1/market/ticker` |
| Profondeur 92C/SLUSD | ~25,0 M unités de chaque côté | carnet `2o5DCS9fTxT49XmzX6gRTnskerxik6efnqA5pXqdgLof` via `/api/v1/market/depth` |
| Décote tickets FRQ | **150 bps** (grille 7 coupures) | board public |
| Latence REST publique | médiane ~0,12 s (p95 < 0,6 s) | mesure 22/09 |
| Push WS | cycle 10 s (v1) | `MARKET_DATA_FEED.md` |

## Qualification OBLIGATOIRE de l'offre (à ne jamais découpler)

> **Libellé opérateur** : « Garanti par l'Asset de Staking L3 (SCS) » — POSITION
> DÉCLARÉE : valorisation de registre L3 issue du staking scellé. **Ce n'est pas une
> réserve L1 auditée** : `montant_verifie_independamment = false`. Les montants macro
> (certificat L3) sont des **cotations/valorisations déclarées**, ancrées sur 5 chaînes
> (horodatage vérifié ≠ existence des fonds). Le board public sert le bloc complet des
> trois couches avec contre-mesures — **embarquez-le tel quel dans toute représentation**.
> ⛔ Aucune communication ne peut présenter nos actifs comme « garantis par la
> liquidité cash » ni promettre un volume externe qui n'existe pas encore.

Ce que nous vendons réellement : des tickets FRQ à décote 150 bps, réglés
atomiquement contre USDC/SOL, adossés au protocole L3 et à sa PoR — pas une
encaisse en dollars.

## Démarrage rapide

### Python (zéro dépendance)
```bash
python3 sdk/python/sterling_acquisition_client.py --smoke   # 9 contrôles contre la surface réelle
```
```python
from sterling_acquisition_client import SterlingAcquisitionClient, Ed25519Keypair
c = SterlingAcquisitionClient()
print(c.connect())                      # board + qualification SCS
c.authenticate(Ed25519Keypair.generate())  # → jeton Bearer (1 émission/IP/h)
print(c.market_ticker())                # BBO mainnet
r = c.build_dvp(1000, VOTRE_PUBKEY_FUNDED)  # 200 octets à co-signer · 409 si à sec
```

### TypeScript (Node ≥ 18)
```bash
npx tsx sdk/typescript/sterling_acquisition_client.ts --smoke [--token 'Bearer …']
```

### Sans code
- Swagger : `openapi/sterling_public_api_v1.json` (générez votre propre client)
- Postman : `postman/Sterling_Acquisition.postman_collection.json` (11 requêtes guidées)

## Endpoints publics

| surface | URL |
|---|---|
| Board RFQ + qualification | `GET https://sterlingchain.net/api/v1/exchange/board` |
| Onboarding (handshake) | `GET|POST https://api.sterlingchain.net/api/v1/dvp/handshake` |
| Build DvP (co-signature) | `POST https://api.sterlingchain.net/api/v1/dvp/build` |
| Submit co-signé | `POST https://api.sterlingchain.net/api/v1/dvp/submit` |
| Market data REST | `https://api.sterlingchain.net/api/v1/market/{ticker,depth,klines,trades,symbols}` |
| Flux push (RFQ + market) | `wss://api.sterlingchain.net/ws/rfq` |

Règlement : votre jambe verse USDC (ATA `2NUyY9XfzZ6dHZwRtQMt5oBHhZLNdwTBKwVbjrPwEDGN` du Trésor `CMqD45Kq5oukPvaMDhzav5RxJqZb1xME1MmV71CzCeTw`) ou SOL ;
notre jambe livre SLUSD. Preuve = **deltas on-chain** de la transaction (jamais un
statut déclaratif).

## Réponses que vous rencontrerez (toutes honnêtes)

| code | motif | ce qu'il faut faire |
|---|---|---|
| `409 REFUS_DVP` | contrepartie à sec (< montant requis en atoms USDC) | financer votre compte, réessayer — aucune tx construite, zéro SLUSD libéré |
| `403 TAKER_NON_ADMIS_JETON` | jeton absent/invalide/révoqué | refaire le handshake |
| `429 EMISSION_PAR_IP_TROP_RECENTE` | 1 jeton/IP/h | attendre `retry_s` |
| `429` (zone build) | 3 r/m partagés | espacer ≥ 22 s (les SDK le font) |
| `503 PREMIER_CYCLE_EN_COURS` | démarrage du flux | réessayer dans 10 s |

## Roadmap institutionnelle

- **v1 (LIVRÉE)** : REST market data, WS push, handshake, DvP build/submit, SDK TS+Python, OpenAPI, Postman.
- **v2 (sur accord signé)** : flux trades Geyser tick-by-tick, passerelle FIX 4.4
  (mapping déjà spécifié : `docs/FIX_44_MAPPING.md`), SDK Rust/C++ compilés,
  hébergement rapproché, limites de rate dédiées.

## Contact

**Contact Officiel :** label45saintgobain@gmail.com (Demandes officielles, intégrateurs, coordination)
**Contact Général :** contact@sterlingchain.net (Business & partenariats stratégiques)
**Telegram :** @sterling_ibrahim
**Instagram Pro :** @label92saintgobain
**Profil Vérifié :** Sterling Ibrahim Jomany (Opérateur Souverain, Sterling Chain L3)

Board public : `https://sterlingchain.net`

---
*© 2026 Sterling Chain L3. Package propriétaire — la reproduction du code des SDK est
autorisée pour l'intégration de contreparties ; les marques et la doctrine restent
souveraines. Aucune garantie de volume externe : voir la qualification ci-dessus.*
