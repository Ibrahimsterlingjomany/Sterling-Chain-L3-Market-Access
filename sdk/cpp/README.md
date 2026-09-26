# SDK C++ (basse latence) — statut et armature (phase 2 institutionnelle)

**État honnête (22/09/2026)** : non implémenté — aucun accord HFT signé à ce jour.
Armature de référence pour un desk C++ (mêmes conventions que Rust/TS/Python) :

- **Signature** : libsodium `crypto_sign_detached(sig, NULL, msg, msglen, sk)`.
  ⚠ msg = octets UTF-8 de la CHAÎNE base64 du nonce (jamais le base64 décodé).
  Clé Solana : seed 32 o → `crypto_sign_seed_keypair` (même courbe ed25519).
- **HTTP/JSON** : Boost.Beast + nlohmann/json (ou cpp-httplib). Endpoints et
  sémantique identiques à `openapi/sterling_public_api_v1.json`.
- **WebSocket** : Boost.Beast `websocket::stream<ssl::stream>` vers
  `wss://api.sterlingchain.net/ws/rfq` ; abonnement `SUBSCRIBE_MARKET` (JSON),
  push toutes les 10 s en v1 (le sous-jacent est le cache du serveur, pas un
  feed Geyser — latence plancher honnête ≈ cycle RPC).
- **Token** : en-tête `Authorization: <token>` TEL QUEL (déjà préfixé Bearer).
- **Latence mesurée de la surface publique** (22/09, n=5, Mac→Hetzner→Mac) :
  REST market 0,10-0,35 s ; push WS ≈ cycle 10 s. Un besoin <100 ms implique un
  hébergement rapproché + flux Geyser dédié = objet de l'accord institutionnel.

Aucune dépendance propriétaire : le protocole est intégralement décrit par
l'OpenAPI + les docs — un desk peut générer son client automatiquement.
