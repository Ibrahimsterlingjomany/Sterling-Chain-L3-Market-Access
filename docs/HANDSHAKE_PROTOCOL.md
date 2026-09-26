# PROTOCOLE D'ONBOARDING `sterling-dvp-handshake/v1`

Objet : obtenir un jeton Bearer permettant de **demander** un devis/une construction DvP.
Le jeton ne garantit AUCUN règlement : le règlement reste atomique co-signé (voir README).

## Étapes

1. `GET /api/v1/dvp/handshake` → termes (standard, algo, TTL 604 800 s, conditions).
2. `POST /api/v1/dvp/handshake` `{"pubkey": "<base58 ed25519>"}` → `{"nonce": "<base64url>", …}`.
   Fenêtre de validité : **120 s**.
3. Signer avec la clé privée du bot : **message = les octets UTF-8 de la CHAÎNE base64 du
   nonce** (`nonce.encode()`), PAS le nonce décodé. ⚠ Piège réel : signer le nonce décodé
   ⇒ `SIGNATURE_ED25519_INVALIDE`. La clé peut être une `Keypair` Solana standard (même courbe).
4. `POST /api/v1/dvp/handshake` `{"pubkey", "nonce", "signature": "<base64 64 o>"}` →
   **201** `{"token": "Bearer <…>", "ttl_s": 604800}`. Le token est **DÉJÀ préfixé** —
   ne jamais re-préfixer (`Bearer Bearer …` ⇒ 403).
5. Appels autorisés : `Authorization: Bearer <…>` sur `/api/v1/dvp/build|submit`.

## Limites (volontaires, ne pas négocier par le code)

| limite | valeur | comportement |
|---|---|---|
| émission de jetons | **1 / IP / heure** | `429 EMISSION_PAR_IP_TROP_RECENTE {retry_s}` |
| jetons actifs | 100 max, révocables individuellement | registre auditable côté opérateur |
| build | 3 r/m (burst 1, zone partagée board/quote/build) | `429` |
| submit | 6 r/m | `429` |
| handshake | 10 r/m | `429` |

## Sécurité

- Nonce stateless `ts‖HMAC` (pas d'état partagé, anti-rejeu par fenêtre 120 s).
- Implémentation ed25519 : RFC 8032 pur Python côté démon ; côté client au choix
  (PyNaCl, solders, tweetnacl, ed25519-dalek, libsodium) — cross-vérifiée par bancs.
- Le jeton maître opérateur n'est JAMAIS rendu par le démon (tag interne).
- ⚠ Un jeton donne le droit de DEMANDER. Les verrous de règlement (G5 contrepartie
  à sec ⇒ 409 REFUS_DVP, co-signature obligatoire, double verrou de diffusion) sont
  DANS le Desk et indépendants du sas.
