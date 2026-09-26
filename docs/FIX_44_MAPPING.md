# PASSERELLE FIX 4.4/5.0 — ARCHITECTURE ET MAPPING (phase 2)

État honnête au 22/09/2026 : **le transport FIX (session TCP Logon/Heartbeat/SeqNum)
n'est PAS déployé**. Ce document est le mapping contractuel + l'architecture de la
passerelle qui sera instanciée pour le PREMIER accord institutionnel signé (moteur
QuickFIX — la passerelle est un pont stateless FIX ⇄ REST/WS Sterling).

## Mapping des messages (FIX 4.4)

| FIX | Sterling | sens |
|---|---|---|
| `Logon (A)` | handshake ed25519 §HANDSHAKE_PROTOCOL (le FIX Password field porte le jeton Bearer ; SenderCompID = pubkey base58 tronquée) | inbound |
| `Heartbeat (0)` / `TestRequest (1)` | keepalive passerelle + ping WS `/ws/rfq` | bidirectionnel |
| `MarketDataRequest (V)` MDEntryTypes=0,1 | `{"action":"SUBSCRIBE_MARKET","channels":["ticker","l2"]}` | inbound |
| `MarketDataSnapshotFullRefresh (W)` | push `channel:"l2"` (bids/asks du snapshot) | outbound |
| `MarketDataRequestReject (Y)` | `SYMBOLE_INCONNU` / `PREMIER_CYCLE_EN_COURS` | outbound |
| `QuoteRequest (R)` | `POST /v1/exchange/quote` (ticket RFQ, montant) | inbound→REST |
| `Quote (S)` | réponse du devis (spread 150 bps grille tickets, ou 1 bp ancre) | outbound |
| `NewOrderSingle (D)` | `POST /api/v1/dvp/build` (ClOrdID = idempotence ; Account = pubkey contrepartie) | inbound→REST |
| `ExecutionReport (8)` ExecType=I (resté) | réponse build : octets tx v0 à co-signer (champ Text = hash du message à signer) | outbound |
| `ExecutionReport (8)` ExecType=F (trade) | `POST /api/v1/dvp/submit` accepté + **deltas on-chain** (preuve de règlement = tx signature + Δ soldes, jamais un statut déclaratif) | outbound |
| `OrderCancelRequest (F)` | sans objet v1 : un build non soumis n'engage rien (aucun état côté Desk au-delà de l'anti-rejeu) | n/a |
| `Reject (3)` / `BusinessMessageReject (j)` | 403 TAKER_NON_ADMIS_JETON / 409 REFUS_DVP (motif brut dans Text) | outbound |

## Champs de référence

- `Symbol` : `SLUSD/USDC` (ancre) · `92C/SLUSD` (profondeur). `SecurityType=FXS` ou `DIGITAL`.
- `Price` : décimales 2/2 (SLUSD, 92C) contre USDC 6 — ⚠ toujours en unités UI du marché,
  jamais en atoms (§ décimales réelles).
- `SettlType` : `T0` atomique (même transaction Solana).
- `OrdType` DvP : ordre à cours limité implicite = parité du ticket (verrou G2 : toute
  demande hors parité ⇒ BusinessMessageReject).

## Architecture de la passerelle (cible)

```
[ OMS MM ]  FIX 4.4 TCP  ──►  [ Passerelle QuickFIX (Mac, loopback) ]
                                   │  Logon → vérif jeton (registre handshake)
                                   │  V/W   → abonné WS wss://…/ws/rfq (SUBSCRIBE_MARKET)
                                   │  R/D/8 → REST api.sterlingchain.net (build/submit/quote)
                                   │  Séq/anti-rejeu FIX assurés par le moteur QuickFIX
                                   └─ zéro clé privée côté passerelle : la co-signature
                                      reste chez la contrepartie (G3)
```

Condition d'instanciation : accord signé + contrepartie funded (la garde G5 du Desk
s'applique à l'identique via FIX — un `NewOrderSingle` d'un compte à sec reçoit un
`ExecutionReport` ExecType=8/Reject `REFUS_DVP`, aucune tx construite).
