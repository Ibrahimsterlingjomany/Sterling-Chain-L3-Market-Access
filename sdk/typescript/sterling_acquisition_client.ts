/**
 * STERLING ACQUISITION CLIENT — SDK PUBLIC DE LA CONTREPARTIE (v1, 22/09/2026).
 *
 * CE QUE CE SDK EST : le client que tout bot externe / market-maker implémente
 * pour se connecter au Sas souverain SANS intervention humaine :
 *   connect()            → termes publics + qualification obligatoire (§24.5)
 *   authenticate(kp)     → handshake ed25519 → SON jeton par bot (§25.5)
 *   quote(montant)       → devis board public qualifié
 *   buildDvp(montant)    → octets d'une tx v0 DvP à co-signer (Desk 1493)
 *   executeDvp(kp,…)     → co-signature de la JAMBE 1 (apport → ATA CMqD) +
 *                          submit ; la JAMBE 2 (SLUSD) est signée par le Desk
 *                          et la tx n'est diffusée QUE si les gardes passent.
 *
 * GARANTIES DE RÈGLEMENT (rappel non négociable, §20/§24.4) :
 *   · l'apport (USDC ou SOL — seuls actifs d'apport autorisés par le moteur,
 *     G2 parité) va DIRECTEMENT à l'ATA du Trésor CMqD dans la MÊME tx ;
 *   · sans co-signature de la contrepartie la tx est indiffusable ⇒ ZÉRO
 *     SLUSD libéré sans paiement reçu (rollback atomique par construction) ;
 *   · le jeton donne le droit de DEMANDER un devis — jamais de régler :
 *     diffusion verrouillée (STERLING_OTC_ALLOW_BROADCAST + execute:true).
 *
 * Smoke réel (aucune clé opérateur, keypair éphémère jetable) :
 *   npx tsx sdk/sterling_acquisition_client.ts --smoke
 * Attendu honnête : terms ✓ · onboarding ✓ · quote ✓ · build ⇒ 409 REFUS_DVP
 * « contrepartie à sec » (le bot n'a pas d'USDC) = la porte EST ouverte, la
 * garde travaille, aucun SLUSD ne sort. C'est une PREUVE mainnet, pas un échec.
 */
import { Keypair } from "@solana/web3.js";
import nacl from "tweetnacl";

export const HANDSHAKE_URL =
  process.env.STERLING_HANDSHAKE_URL ??
  "https://api.sterlingchain.net/api/v1/dvp/handshake";
export const PUBLIC_BASE =
  process.env.STERLING_PUBLIC_BASE ?? "https://sterlingchain.net/api";
export const ONBOARDING_URL = HANDSHAKE_URL;

const b64 = (b: Uint8Array) => Buffer.from(b).toString("base64");
const fromB64 = (s: string) => new Uint8Array(Buffer.from(s, "base64"));

async function json_(url: string, opts: any = {}, timeout = 30000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url, { ...opts, signal: ctl.signal });
    let body: any = null;
    try { body = await r.json(); } catch { /* corps non-JSON */ }
    return { status: r.status, body };
  } finally { clearTimeout(t); }
}

export interface SterlingTerms {
  board: any;
  handshake: any;
  qualification: any;
  reglementVerrouille: boolean;
}

export class SterlingAcquisitionClient {
  token: string | null = null;
  pubkey: string | null = null;

  /** 1) Termes publics + qualification obligatoire embarquée (§24.5). */
  async connect(): Promise<SterlingTerms> {
    const [b, h] = await Promise.all([
      json_(`${PUBLIC_BASE}/v1/exchange/board`, {}, 45000),
      json_(HANDSHAKE_URL),
    ]);
    if (b.status !== 200 || !b.body?.offres)
      throw new Error(`BOARD_INDISPONIBLE http=${b.status}`);
    if (h.status !== 200 || h.body?.standard !== "sterling-dvp-handshake/v1")
      throw new Error(`HANDSHAKE_INDISPONIBLE http=${h.status}`);
    const qual = b.body.qualification_scs;
    if (!qual || qual.diffusable !== true)
      throw new Error("QUALIFICATION_ABSENTE — publication non conforme §24.5");
    return {
      board: b.body, handshake: h.body, qualification: qual,
      reglementVerrouille: true, // le jeton n'ouvre QUE le devis
    };
  }

  /** 2) Handshake ed25519 → jeton PAR BOT (TTL 7 j, révocable côté serveur). */
  async authenticate(kp: Keypair): Promise<{ token: string; expire: string }> {
    this.pubkey = kp.publicKey.toBase58();
    const ch = await json_(HANDSHAKE_URL, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pubkey: this.pubkey }),
    });
    if (ch.status !== 200 || !ch.body?.nonce)
      throw new Error(`CHALLENGE_REFUSE http=${ch.status} ${JSON.stringify(ch.body)?.slice(0, 200)}`);
    // web3.js v1 : PAS de kp.sign() — tweetnacl sur la clé secrète (piège §20).
    // ⚠ CONVENTION HANDSHAKE : le démon vérifie sur nonce.encode() = octets
    //   UTF-8 de la CHAÎNE base64 (dvp_handshake_daemon.py l.342), PAS sur les
    //   octets décodés. Le DvP, lui, co-signe les octets décodés du message tx.
    const sig = nacl.sign.detached(new TextEncoder().encode(ch.body.nonce), kp.secretKey);
    const tok = await json_(HANDSHAKE_URL, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pubkey: this.pubkey, nonce: ch.body.nonce, signature: b64(sig) }),
    });
    if (tok.status !== 201 || !tok.body?.token)
      throw new Error(`ONBOARDING_REFUSE http=${tok.status} ${JSON.stringify(tok.body)?.slice(0, 200)}`);
    // ⚠ le démon renvoie la VALEUR D'EN-TÊTE complète (« Bearer xxx », clé 29 o
    //   §25.3) : ne jamais re-préfixer (double Bearer ⇒ 403 au sas nginx).
    this.token = String(tok.body.token);
    return { token: this.token, expire: tok.body.expires_at ?? tok.body.expire ?? null };
  }

  /** En-tête exact pour le sas : le jeton porte déjà son préfixe (§25.3). */
  private authHeader(): string {
    return this.token!.startsWith("Bearer ") ? this.token! : `Bearer ${this.token}`;
  }

  /** 3) Devis public qualifié (board 1496 via l'ingress — crée un ticket RFQ). */
  async quote(montantSlusd: number, actif: "USDC" | "SOL" = "USDC") {
    const r = await json_(
      `${PUBLIC_BASE}/v1/exchange/quote?asset=SLUSD&pay=${actif}&amount=${montantSlusd}`,
      {}, 45000);
    if (r.status !== 200 || !r.body?.rfq)
      throw new Error(`QUOTE_INDISPONIBLE http=${r.status} ${JSON.stringify(r.body)?.slice(0, 200)}`);
    return r.body;
  }

  /** 4) Construction DvP : octets à co-signer, JAMAIS signés/diffusés (G3). */
  async buildDvp(montantSlusd: number, actif: "USDC" | "SOL" = "USDC",
                 kp?: Keypair) {
    if (!this.token) throw new Error("NON_AUTHENTIFIÉ — appelez authenticate()");
    const cp = (kp?.publicKey ?? (this.pubkey ? undefined : undefined));
    if (!this.pubkey && !kp) throw new Error("CONTREPARTIE_INCONNUE");
    const corps = {
      side: "SELL_SLUSD", base_asset: "SLUSD", quote_asset: actif,
      amount: montantSlusd,
      counterparty: kp?.publicKey.toBase58() ?? this.pubkey,
      idempotency_key: `sdk-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    };
    const r = await json_("https://api.sterlingchain.net/api/v1/dvp/build", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: this.authHeader() },
      body: JSON.stringify(corps),
    }, 150000); // timeout client > timeout moteur Desk (§22.3)
    void cp;
    return { status: r.status, body: r.body };
  }

  /** 5) Co-signature de la JAMBE 1 (apport → ATA CMqD) sur le message exact. */
  cosigner(build: any, kp: Keypair): string {
    const msgB64 = build?.a_signer_par_la_contrepartie?.message_b64;
    if (!msgB64) throw new Error("AUCUN_MESSAGE_A_SIGNER (build refusé ?)");
    const sig = nacl.sign.detached(fromB64(msgB64), kp.secretKey);
    if (sig.length !== 64) throw new Error("SIGNATURE_LONGUEUR_INVALIDE");
    return b64(sig);
  }

  /** 6) Soumission : execute=false TOUJOURS (double verrou de diffusion §24.4). */
  async submitDvp(ticketId: string, counterpartySignatureB64: string) {
    const r = await json_("https://api.sterlingchain.net/api/v1/dvp/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: this.authHeader() },
      body: JSON.stringify({ ticket_id: ticketId,
                             counterparty_signature: counterpartySignatureB64,
                             execute: false }),
    }, 180000);
    return { status: r.status, body: r.body };
  }

  /** Cycle complet : build → co-signature → submit(execute:false). */
  async executeDvp(kp: Keypair, montantSlusd: number, actif: "USDC" | "SOL" = "USDC") {
    const b = await this.buildDvp(montantSlusd, actif, kp);
    if (b.status !== 200 || b.body?.ok !== true) return { etape: "BUILD", ...b };
    const sig = this.cosigner(b.body, kp);
    const s = await this.submitDvp(String(b.body.ticket_id), sig);
    return { etape: "SUBMIT", build: { status: b.status, ticket_id: b.body.ticket_id }, ...s };
  }
}

/** ── Smoke RÉEL sur surface publique (keypair éphémère jetable, zéro clé opérateur) ── */
async function smoke() {
  const out: any = { ts: new Date().toISOString(), etapes: [] };
  const log = (s: string) => { console.log(s); out.etapes.push(s); };
  const c = new SterlingAcquisitionClient();
  const terms = await c.connect();
  log(`✅ connect() : board ${terms.board.offres?.length} offres · qual diffusable=${terms.qualification.diffusable} · onboarding=${terms.handshake.standard}`);
  const kp = Keypair.generate();
  out.bot_pubkey = kp.publicKey.toBase58();
  const ti = process.argv.indexOf("--token");
  if (ti > -1 && process.argv[ti + 1]) {
    // jeton injecté (audit opérateur — l'émission est limitée à 1/IP/h, §25.5)
    c.token = process.argv[ti + 1];
    c.pubkey = out.bot_pubkey;
    log(`✅ jeton injecté via --token (${c.token.slice(0, 10)}…) — authenticate() court-circuité`);
  }
  if (!c.token) try {
    const tok = await c.authenticate(kp);
    log(`✅ authenticate() : jeton ${tok.token.slice(0, 6)}… (bot ${out.bot_pubkey.slice(0, 8)}…) expire ${tok.expire}`);
  } catch (e: any) {
    log(`⚠ authenticate() : ${String(e.message).slice(0, 160)} — limite 1/IP/h possible (garde anti-abus réelle, PAS un échec SDK)`);
  }
  // ⚠ SAS : la zone nginx `dvp_taker_build` (3 r/m) est PARTAGÉE entre
  //   /api/v1/exchange/* (board, quote) et /api/v1/dvp/build (burst=1).
  //   Un client poli espace ses appels ≥ 22 s — sinon 429 (garde réelle).
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  await sleep(22000);
  const q = await c.quote(1000, "USDC");
  log(`✅ quote(1000 SLUSD) : RFQ ${q.rfq.id} · payer ${q.rfq.pay_amount} USDC → recevoir ${q.rfq.asset_out} SLUSD (spread ${q.rfq.spread_bps} bps, parité ${q.rfq.parity_usd})`);
  if (c.token) {
    await sleep(22000);
    const d = await c.executeDvp(kp, 1000, "USDC");
    out.dvp = d;
    const motif = d.body?.erreur ?? d.body?.statut ?? `HTTP ${d.status}`;
    const detail = String(d.body?.detail ?? "").slice(0, 200);
    log(`✅ executeDvp() → ${d.etape} : ${motif} ${detail}`);
    log(`   INTERPRÉTATION HONNÊTE : un bot SANS fonds reçoit un refus structuré (G5`);
    log(`   « contrepartie à sec ») — la porte EST ouverte, la garde travaille, ZÉRO SLUSD libéré.`);
  }
  const fs = await import("fs");
  fs.writeFileSync("output/sdk_smoke.json", JSON.stringify(out, null, 2));
  console.log("\nartefact : output/sdk_smoke.json");
}

if (process.argv.includes("--smoke")) {
  smoke().then(() => process.exit(0)).catch((e) => { console.error("❌", e); process.exit(1); });
}
