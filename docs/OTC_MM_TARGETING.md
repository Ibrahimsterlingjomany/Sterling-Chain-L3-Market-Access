# CIBLAGE MARKET MAKERS & DESKS OTC — protocole d'intégration institutionnel

État des lieux HONNÊTE (vérifié le 22/09/2026 par sondes réelles, `tools/otc_mm_probe.py`) :
**AUCUN market maker majeur n'expose d'API d'intake RFQ en self-service sans accord
cadre.** La connexion aux acteurs ci-dessous est un acte CONTRACTUEL (business
onboarding), pas un branchement de code. Ce qui EST autonome et live côté Sterling :
board public, flux WS, handshake ed25519 ouvert à tout bot, market data REST, SDK —
le terrain technique est prêt à 100 % pour le premier accord.

## Liste de ciblage (compatibilité Solana publique + voie d'intégration)

| # | acteur | type | Solana | voie d'intégration |
|---|---|---|---|---|
| 1 | **Wintermute** | MM + OTC | ✓ (public) | institutional onboarding (form + BD) ; pas d'API self-serve |
| 2 | **GSR** | MM | ✓ | accord cadre ; desk OTC via leur sales |
| 3 | **Flowdesk** | MM (Paris) | ✓ | accord cadre ; ouverts aux profils émergents |
| 4 | **Auros** | MM | ✓ | accord cadre (Asia) |
| 5 | **Keyrock** | MM (EU) | ✓ | accord cadre ; programme listings |
| 6 | **Selini Capital** | MM/HFT | ✓ | accord cadre (ex-Jump) |
| 7 | **Pulsar Trading** | MM | ✓ | accord cadre |
| 8 | **Kronos Research** | MM/HFT | ✓ | accord cadre |
| 9 | **DWF Labs** | MM/invest | ✓ | accord cadre (deal flow rapide) |
| 10 | **Amber Group** | MM/OTC | ✓ | accord cadre |
| 11 | **QCP Capital** | OTC (Asia) | ✓ | accord OTC bilatéral |
| 12 | **B2C2** | OTC inst. | ✓ | accord OTC ; exigent volumes |
| 13 | **Cumberland (DRW)** | OTC inst. | ✓ | accord OTC ; très sélectif |
| 14 | **FalconX** | OTC inst. | ✓ | accord OTC |
| 15 | **Galaxy Digital** | OTC inst. | ✓ | accord OTC |
| 16 | **Jump Trading** | MM/HFT | ✓ | hyper-sélectif, via partnership |

Agrégateurs/indexeurs (aucune action contractuelle possible — ils lisent l'on-chain) :
**Jupiter** route DÉJÀ nos carnets (mesuré : premier saut SLUSD→USDC = `6aKy…`) ;
**DexScreener** ne couvre pas OpenBook v2 (0 paire mesurée) ; **BirdEye** lit les
vaults (TVL). ⛔ Aucune « publication » par API n'existe chez eux (§25.6) — ne
jamais prétendre le contraire dans un pitch.

## Kit d'envoi (payload prêt)

`reports/otc_mm_payload.txt` — message type (EN) conforme §24.5 : qualification des
trois couches EMBARQUÉE, chiffres mesurés uniquement, libellé « Garanti par l'Asset
de Staking L3 (SCS) » jamais nu, liens vers le package public :

- README : `https://api.sterlingchain.net/public-sdk/README.md`
- OpenAPI : `https://api.sterlingchain.net/public-sdk/openapi/sterling_public_api_v1.json`
- SDK Python (9/9 smoke public) : `…/public-sdk/sdk/python/sterling_acquisition_client.py`
- SDK TS : `…/public-sdk/sdk/typescript/sterling_acquisition_client.ts`
- Postman : `…/public-sdk/postman/Sterling_Acquisition.postman_collection.json`
- Board live : `https://sterlingchain.net/api/v1/exchange/board`

## Règles d'envoi (non négociables)

1. ⛔ Ne JAMAIS écrire « garanti par la liquidité cash », « 40/40 garanti », ni citer
   290 T / 60 T comme réserve disponible — uniquement comme COTATION L3 avec
   `montant_verifie_independamment=false`.
2. ✓ Toujours joindre le bloc de qualification (le board le sert en JSON : champ
   `qualification_scs`).
3. ✓ Annoncer la réalité du règlement : DvP atomique co-signé, G5 refuse une
   contrepartie à sec, preuve = deltas on-chain.
4. ✓ Demander LEUR canal : « donnez-nous votre intake API / contact onboarding,
   voici notre surface publique fonctionnelle » — jamais promettre de volume externe
   qui n'existe pas (§21 : mesuré 0,999900 USDC de sortie quelle que soit la taille).
5. Après premier contact : handshake dédié (jeton longue durée), rate limit own-zone,
   passerelle FIX v2 (mapping déjà spécifié).
