# FLUX MARKET DATA — Sterling Chain L3 (v1, 22/09/2026)

Source unique de vérité : les carnets **OpenBook v2 mainnet** (CLOB natif, zéro CPMM).
Lecture seule — ce service ne passe aucun ordre, ne déplace aucun fonds.

| marché | rôle | adresse |
|---|---|---|
| SLUSD/USDC | ANCRE — oracle facial 1:1 (balise, micro-ordres) | `6aKy9pZP73oysFGmbCcpBUNMFNqVj4ZcLBSQ7fX5Mumu` |
| 92C/SLUSD | PROFONDEUR — TVL souveraine | `2o5DCS9fTxT49XmzX6gRTnskerxik6efnqA5pXqdgLof` |

## 1. REST (cache servi depuis le cycle 10 s — latence mesurée 0,10-0,35 s)

Base : `https://api.sterlingchain.net/api/v1/market` · rate limit **60 r/m/IP (burst 20)** · CORS `*`.

| route | contenu |
|---|---|
| `GET /ticker?symbol=SLUSD/USDC` | BBO : `bid`, `ask`, `mid`, `spread_bps`, `ts`, `market`, `role`, `attribution_profondeur`, `honnete.volume_24h=null` |
| `GET /depth?symbol=…&limit=20` | L2 agrégé : `bids:[{price,size}]`, `asks:[…]` |
| `GET /klines?symbol=…&limit=100` | bougies **1m** `[ts,o,h,l,c]` sur le mid BBO, agrégées depuis le service (append-only, aucune donnée inventée) |
| `GET /trades?symbol=…` | **traces v1** : `eventHeap{count,seqNum}` (fills non consommés) + 5 dernières signatures du marché. ⚠ PAS un fill feed tick-by-tick Geyser — v2 sur accord institutionnel |
| `GET /symbols` | marchés servis + rôles + doctrine |

Réponses d'erreur honnêtes : `503 PREMIER_CYCLE_EN_COURS` (démarrage), `404 SYMBOLE_INCONNU`, `429` (zone).

## 2. WebSocket (push)

`wss://api.sterlingchain.net/ws/rfq` — même endpoint que le flux RFQ (channels distincts).

1. À la connexion : `WELCOME` (grille de coupures, PoR, avertissement règlement).
2. Abonnement market data :
```json
{"action":"SUBSCRIBE_MARKET","channels":["ticker","l2","trades"],"symbols":["SLUSD/USDC"]}
```
→ accusé `{"event":"SUBSCRIBED", …}`. `symbols` omis = tous les marchés.
3. Push à chaque cycle (10 s) : `{"channel":"ticker","symbol":"SLUSD/USDC","data":{…}}`.
4. Sans abonnement, AUCUN message market n'est poussé (flux RFQ historique inchangé).

Événements RFQ sur le même socket : `NEW_FRQ_TICKET` (offre, décote 150 bps, timeout 75 slots),
`TICKET_SETTLED`, `POR_STATUS`. Claim : `{"action":"CLAIM","ticket_id":"TR-…","bot_id":"…"}`.

## 3. SÉMANTIQUE HONNÊTE (non négociable)

- `attribution_profondeur = DESK_SOUS_PREUVE_DU_CONTRAIRE` : la profondeur au repos est
  celle du Desk souverain jusqu'à preuve positive d'un tiers (§ inversion de la charge).
- `volume_24h = null` : aucune contrepartie externe mesurée à ce jour — jamais inventé.
- Les ticks observés (ancre) : bid 0,9999 / ask 1,0000 — spread facial 1,0 bps.
- Le canal `trades` v1 expose des TRACES on-chain vérifiables, pas un flux ms-par-ms.
