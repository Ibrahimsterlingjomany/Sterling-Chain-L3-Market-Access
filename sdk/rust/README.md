# SDK Rust — statut et armature (phase 2 institutionnelle)

**État honnête (22/09/2026)** : le SDK de référence opérationnel est TypeScript
(`sdk/typescript/`) et Python (`sdk/python/`, smoke 9/9 contre la surface publique).
Le client Rust ci-dessous est une ARMATURE COMPLETE pour la couche critique
(handshake ed25519 + build DvP) — à compiler par la contrepartie institutionnelle
ou par nous à la signature du premier accord MM (cargo crate publiée à ce moment).

## Dépendances

```toml
[dependencies]
ed25519-dalek = "2"      # signature (RFC 8032, même courbe que Solana)
rand = "0.8"
reqwest = { version = "0.12", features = ["json", "rustls-tls"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
tokio-tungstenite = { version = "0.24", features = ["rustls-tls-webpki-roots"] }  # flux WS market/RFQ
bs58 = "0.5"
base64 = "0.22"
```

## Handshake — code exact (conventions §HANDSHAKE_PROTOCOL)

```rust
use ed25519_dalek::{SigningKey, Signer};

// ⚠ CONVENTION NON NÉGOCIABLE : le message signé = les octets UTF-8 de la
// CHAÎNE base64 du nonce (nonce.as_bytes()), PAS le nonce décodé.
async fn authenticate(client: &reqwest::Client, sk: &SigningKey) -> anyhow::Result<String> {
    let pubkey = bs58::encode(sk.verifying_key().as_bytes()).into_string();
    let ch: serde_json::Value = client
        .post("https://api.sterlingchain.net/api/v1/dvp/handshake")
        .json(&serde_json::json!({ "pubkey": pubkey }))
        .send().await?.error_for_status()?.json().await?;
    let nonce = ch["nonce"].as_str().unwrap().to_string();
    let sig = sk.sign(nonce.as_bytes());          // ← UTF-8 de la chaîne base64
    let rep: serde_json::Value = client
        .post("https://api.sterlingchain.net/api/v1/dvp/handshake")
        .json(&serde_json::json!({
            "pubkey": pubkey, "nonce": nonce,
            "signature": base64::Engine::encode(&base64::engine::general_purpose::STANDARD, sig.to_bytes()),
        }))
        .send().await?.error_for_status()?.json().await?;   // 201 Created
    // Le token est DÉJÀ préfixé « Bearer … » — ne JAMAIS re-préfixer.
    Ok(rep["token"].as_str().unwrap().to_string())
}
```

## Build DvP (execute=false PAR CONCEPTION)

```rust
let token = authenticate(&client, &sk).await?;    // ou jeton existant (1/IP/h !)
let build = client.post("https://api.sterlingchain.net/api/v1/dvp/build")
    .header("Authorization", token.clone())       // token déjà préfixé
    .json(&serde_json::json!({
        "montant_slusd": 1000.0,
        "contrepartie": VOTRE_PUBKEY_SOLANA,      // compte funded USDC/SOL (garde G5)
        "execute": false                          // ⛔ toujours false côté client
    }))
    .send().await?;                                // 200 = octets à co-signer · 409 = REFUS_DVP
```

Co-signature : la tx v0 retournée se signe avec `solana-sdk` (`VersionedTransaction`),
puis `POST /api/v1/dvp/submit`. Le Desk simule et ne diffuse que si ses propres
verrous sont levés — la preuve de règlement = **deltas on-chain**, jamais un statut.

## WS market data

```rust
// wss://api.sterlingchain.net/ws/rfq → envoyer :
// {"action":"SUBSCRIBE_MARKET","channels":["ticker","l2","trades"],"symbols":["SLUSD/USDC"]}
```

Rate limits à respecter côté client : ≥22 s entre build/quote/submit (zone 3 r/m),
60 r/m sur market data, 1 émission de jeton/IP/h.
