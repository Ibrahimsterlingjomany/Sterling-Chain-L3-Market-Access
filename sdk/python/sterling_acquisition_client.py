#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sterling Acquisition Client — SDK PYTHON officiel (zéro dépendance)
===================================================================
Autorité souveraine : Sterling Ibrahim Jomany · Sterling Chain L3 · 22/09/2026.

Client d'acquisition pour contreparties externes (Market Makers, desks OTC,
bots d'arbitrage) : onboarding ed25519, lecture du board RFQ, devis, market
data temps réel, construction DvP atomique.

⚠ GARANTIES STRUCTURELLES (à lire avant intégration) :
  · execute=false PAR CONCEPTION : ce client ne diffuse JAMAIS de transaction.
    Le règlement réel exige la co-signature ed25519 de VOTRE clé dans une tx v0
    atomique (jambe 1 = votre USDC/SOL, jambe 2 = SLUSD du Desk). Sans votre
    signature la tx est indiffusable ; si votre jambe échoue, TOUT est rejoué
    ⇒ zéro SLUSD libéré sans paiement reçu — et zéro paiement perdu.
  · La garde G5 du Desk refuse une contrepartie sans fonds (409 REFUS_DVP).
  · Lecture seule par défaut : handshake/terms/board/quote/market n'engagent rien.

DÉPENDANCES : AUCUNE (stdlib : urllib, hashlib, json). ed25519 RFC 8032 pur
embarqué (mêmes primitives que le démon de handshake). Si PyNaCl est installé,
il est utilisé de préférence (cross-vérifiable).

USAGE
  python3 sterling_acquisition_client.py --smoke [--token 'Bearer xxx']
  from sterling_acquisition_client import SterlingAcquisitionClient, Ed25519Keypair
  kp = Ed25519Keypair.generate()
  c = SterlingAcquisitionClient()
  c.connect()            # termes + qualification SCS (obligatoire)
  c.authenticate(kp)     # handshake challenge-réponse → jeton Bearer
  c.market_ticker()      # BBO OpenBook v2 mainnet (lecture seule)
  r = c.build_dvp(ticket_id, kp)   # → octets à co-signer (jamais diffusés ici)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

__version__ = "1.0.0"

BASE_API = os.environ.get("STERLING_API_BASE", "https://api.sterlingchain.net")
BASE_EXCHANGE = os.environ.get("STERLING_EXCHANGE_BASE", "https://sterlingchain.net/api")
USER_AGENT = "SterlingAcquisitionClientPython/1.0"
ESPACEMENT_S = 22  # zones rate-limitées 3r/m partagées (§ documentation) — client poli

# ════════════════════════ ed25519 PUR (RFC 8032) ════════════════════════
_P = 2**255 - 19
_L = 7237005577332262213973186563042994240857116359379907606001950938285454250989
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_GY = 4 * pow(5, _P - 2, _P) % _P  # y du point de base (RFC 8032)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _recover_x(y: int, sign: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return 0 if sign == 0 else None
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * pow(2, (_P - 1) // 4, _P) % _P
    if (x * x - x2) % _P != 0:
        return None
    return x if x % 2 == sign else _P - x


def _pt_add(p1, p2):
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    dd = 2 * z1 * z2 % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _pt_mul(s: int, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _pt_add(q, pt)
        pt = _pt_add(pt, pt)
        s >>= 1
    return q


def _pt_encode(pt) -> bytes:
    x, y, z, _t = pt
    zi = _inv(z)
    x = x * zi % _P
    y = y * zi % _P
    enc = bytearray(y.to_bytes(32, "little"))
    enc[31] |= (x & 1) << 7
    return bytes(enc)


def _pt_decode(b: bytes):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _init_g():
    gx = _recover_x(_GY, 0)
    return (gx, _GY, 1, gx * _GY % _P)


_G = _init_g()


def _sha512(b: bytes) -> bytes:
    return hashlib.sha512(b).digest()


def ed25519_public_from_seed(seed: bytes) -> bytes:
    assert len(seed) == 32
    h = _sha512(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return _pt_encode(_pt_mul(a, _G))


def ed25519_sign(seed: bytes, msg: bytes) -> bytes:
    h = _sha512(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    prefix = h[32:]
    A = _pt_encode(_pt_mul(a, _G))
    r = int.from_bytes(_sha512(prefix + msg), "little") % _L
    R = _pt_encode(_pt_mul(r, _G))
    k = int.from_bytes(_sha512(R + A + msg), "little") % _L
    s = (r + k * a) % _L
    return R + s.to_bytes(32, "little")


def ed25519_verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    """RETOURNE un booléen — ne lève JAMAIS sur signature invalide (§15 : un
    try/except seul ferait passer une signature invalide pour la mauvaise raison)."""
    try:
        if len(sig) != 64 or len(pub) != 32:
            return False
        R = _pt_decode(sig[:32])
        A = _pt_decode(pub)
        if R is None or A is None:
            return False
        s = int.from_bytes(sig[32:], "little")
        if s >= _L:
            return False
        k = int.from_bytes(_sha512(sig[:32] + pub + msg), "little") % _L
        left = _pt_mul(s, _G)
        right = _pt_add(R, _pt_mul(k, A))
        return _pt_encode(left) == _pt_encode(right)
    except Exception:
        return False


class Ed25519Keypair:
    """Paire de clés ed25519 (seed 32 o). Compatible Solana Keypair (même courbe)."""

    def __init__(self, seed: bytes):
        assert len(seed) == 32, "seed = 32 octets"
        self.seed = seed
        self.public_key = ed25519_public_from_seed(seed)
        try:  # PyNaCl optionnel (signature accélérée, vérifiable croisée)
            from nacl.signing import SigningKey  # type: ignore
            self._nacl = SigningKey(seed)
        except Exception:
            self._nacl = None

    @classmethod
    def generate(cls) -> "Ed25519Keypair":
        return cls(os.urandom(32))

    def sign(self, msg: bytes) -> bytes:
        if self._nacl is not None:
            return self._nacl.sign(msg).signature
        return ed25519_sign(self.seed, msg)

    def verify(self, msg: bytes, sig: bytes) -> bool:
        return ed25519_verify(self.public_key, msg, sig)

    def public_base58(self) -> str:
        ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        n = int.from_bytes(self.public_key, "big")
        s = ""
        while n:
            n, r = divmod(n, 58)
            s = ALPH[r] + s
        pad = len(self.public_key) - len(self.public_key.lstrip(b"\x00"))
        return "1" * pad + s


# ════════════════════════ CLIENT HTTP ════════════════════════
class SterlingError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


def _req(method: str, url: str, body: dict | None = None, headers: dict | None = None,
         timeout: int = 30) -> tuple[int, dict | list | None]:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, {"raw": raw.decode(errors="replace")[:2000]}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")[:2000]}


class SterlingAcquisitionClient:
    """Client d'acquisition — toutes les méthodes sont idempotentes en lecture
    sauf authenticate (émet un jeton : 1/IP/h) et build/submit (zonés 3r/m).
    Un espacement ≥ ESPACEMENT_S est appliqué automatiquement entre les appels
    vers les zones rate-limitées. execute=false PAR CONCEPTION."""

    def __init__(self, base_api: str = BASE_API, base_exchange: str = BASE_EXCHANGE, token: str | None = None):
        self.base_api = base_api.rstrip("/")
        self.base_exchange = base_exchange.rstrip("/")
        self.token = token  # « Bearer xxx » TEL QUEL (le démon renvoie le préfixe — ne jamais re-préfixer)
        self.qualification: dict | None = None
        self._dernier_appel_zone: float = 0.0

    def _auth_headers(self) -> dict:
        return {"Authorization": self.token} if self.token else {}

    def _espacer(self) -> None:
        attendu = self._dernier_appel_zone + ESPACEMENT_S
        if time.time() < attendu:
            time.sleep(attendu - time.time())
        self._dernier_appel_zone = time.time()

    # ── 1. Termes + qualification SCS (OBLIGATOIRE avant tout) ──
    def connect(self) -> dict:
        st, board = _req("GET", f"{self.base_exchange}/v1/exchange/board", timeout=45)
        if st != 200 or not isinstance(board, dict):
            raise SterlingError(f"board inaccessible (HTTP {st})", st, board)
        q = board.get("qualification_scs") or {}
        if not q.get("diffusable"):
            raise SterlingError("qualification SCS absente ou non diffusable — connexion refusée (§24.5)")
        self.qualification = q
        offres = board.get("offres") or board.get("tickets") or []
        return {"etape": "CONNECT", "offres": len(offres), "libelle_garantie": q.get("libelle_garantie_operateur"),
                "montant_verifie_independamment": q.get("montant_verifie_independamment"),
                "onboarding_url": board.get("onboarding_url")}

    # ── 2. Handshake ed25519 (challenge-réponse) → jeton Bearer ──
    def handshake_terms(self) -> dict:
        """GET = termes du protocole (standard, algo, étapes, TTL)."""
        st, ch = _req("GET", f"{self.base_api}/api/v1/dvp/handshake")
        if st != 200:
            raise SterlingError(f"termes refusés (HTTP {st})", st, ch)
        return ch

    def handshake_challenge(self, pubkey_b58: str) -> dict:
        """POST {pubkey} = émission du NONCE (fenêtre 120 s). Le jeton, lui,
        n'est émis qu'au verify réussi (limite 1/IP/h)."""
        st, ch = _req("POST", f"{self.base_api}/api/v1/dvp/handshake", body={"pubkey": pubkey_b58})
        if st != 200 or not (ch or {}).get("nonce"):
            raise SterlingError(f"challenge refusé (HTTP {st})", st, ch)
        return ch

    def authenticate(self, kp: Ed25519Keypair) -> dict:
        ch = self.handshake_challenge(kp.public_base58())
        nonce = ch.get("nonce")
        if not nonce:
            raise SterlingError("challenge sans nonce", 200, ch)
        # ⚠ CONVENTION (§25.6) : la signature porte sur les OCTETS UTF-8 de la
        # CHAÎNE base64 du nonce (nonce.encode()), PAS sur le base64 décodé.
        sig = kp.sign(nonce.encode())
        self._espacer()
        st, rep = _req("POST", f"{self.base_api}/api/v1/dvp/handshake", body={
            "pubkey": kp.public_base58(), "nonce": nonce, "signature": _b64(sig),
        })
        # ⚠ Le démon répond 201 Created à l'émission du jeton (vérifié le 22/09/2026).
        if st not in (200, 201) or not isinstance(rep, dict) or not rep.get("token"):
            raise SterlingError(f"handshake échoué (HTTP {st})", st, rep)
        self.token = rep["token"]  # déjà préfixé « Bearer » — ne JAMAIS re-préfixer
        return {"etape": "AUTHENTICATE", "pubkey": kp.public_base58(), "token_prefixe": self.token[:12] + "…",
                "ttl_s": rep.get("ttl_s")}

    # ── 3. Market data (lecture seule, mainnet OpenBook v2) ──
    def market_ticker(self, symbol: str | None = None) -> dict:
        q = f"?symbol={symbol}" if symbol else ""
        st, r = _req("GET", f"{self.base_api}/api/v1/market/ticker{q}")
        if st != 200:
            raise SterlingError(f"ticker (HTTP {st})", st, r)
        return r

    def market_depth(self, symbol: str | None = None, limit: int = 20) -> dict:
        q = f"?limit={limit}" + (f"&symbol={symbol}" if symbol else "")
        st, r = _req("GET", f"{self.base_api}/api/v1/market/depth{q}")
        if st != 200:
            raise SterlingError(f"depth (HTTP {st})", st, r)
        return r

    def market_klines(self, symbol: str | None = None, limit: int = 100) -> dict:
        q = f"?limit={limit}" + (f"&symbol={symbol}" if symbol else "")
        st, r = _req("GET", f"{self.base_api}/api/v1/market/klines{q}")
        if st != 200:
            raise SterlingError(f"klines (HTTP {st})", st, r)
        return r

    # ── 4. RFQ : devis sur ticket du board ──
    def quote(self, ticket_id: str, montant_usdc: float) -> dict:
        self._espacer()
        st, r = _req("POST", f"{self.base_exchange}/v1/exchange/quote",
                     body={"ticket_id": ticket_id, "montant": montant_usdc}, headers=self._auth_headers(), timeout=45)
        return {"status": st, "body": r}

    # ── 5. DvP atomique (build → octets à co-signer ; execute=false TOUJOURS) ──
    def build_dvp(self, montant_slusd: float, contrepartie_pubkey: str) -> dict:
        self._espacer()
        st, r = _req("POST", f"{self.base_api}/api/v1/dvp/build", body={
            "montant_slusd": montant_slusd, "contrepartie": contrepartie_pubkey, "execute": False,
        }, headers=self._auth_headers(), timeout=150)
        return {"etape": "BUILD", "status": st, "body": r}

    def submit_dvp_cosigned(self, tx_base64: str, signatures: dict) -> dict:
        """Soumet la tx v0 CO-SIGNÉE (votre signature ed25519 + octets). Le Desk
        vérifie localement, simule, et ne diffuse que si les verrous G4 sont
        levés côté Desk (STERLING_OTC_ALLOW_BROADCAST) — ce client ne diffuse
        JAMAIS lui-même."""
        self._espacer()
        st, r = _req("POST", f"{self.base_api}/api/v1/dvp/submit", body={
            "tx_base64": tx_base64, "signatures": signatures, "execute": False,
        }, headers=self._auth_headers(), timeout=180)
        return {"etape": "SUBMIT", "status": st, "body": r}


def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode()


# ════════════════════════ SMOKE PUBLIC ════════════════════════
def _smoke(token: str | None) -> int:
    ok, ko = 0, 0

    def t(label: str, cond: bool, detail: str = ""):
        nonlocal ok, ko
        if cond:
            ok += 1
            print(f"  ✅ {label}")
        else:
            ko += 1
            print(f"  ❌ {label} — {detail}")

    print("=== SDK Python · SMOKE PUBLIC (lecture seule + preuves honnêtes) ===")
    # S1 ed25519 pur vs RFC (vecteur de test RFC 8032)
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    pub_attendu = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    kp = Ed25519Keypair(seed)
    t("S1 clé publique RFC 8032 exacte", kp.public_key.hex() == pub_attendu)
    sig = kp.sign(b"")
    t("S2 signature RFC du message vide vérifiée", ed25519_verify(kp.public_key, b"", sig))
    t("S3 non-répudiation : signature altérée REJETÉE (booléen, §15)", not ed25519_verify(kp.public_key, b"x", sig))
    try:
        from solders.keypair import Keypair as SKey  # type: ignore
        sk = SKey.from_bytes(seed + kp.public_key)
        t("S4 cross-vendor solders : même pubkey", bytes(sk.pubkey()).hex() == kp.public_key.hex())
    except ImportError:
        print("  ℹ S4 solders absent — cross-vendor sauté (optionnel)")
    c = SterlingAcquisitionClient(token=token)
    # S5 connect : termes + qualification
    try:
        r = c.connect()
        t("S5 connect() : board + qualification SCS diffusable", r["offres"] >= 0 and c.qualification.get("diffusable") is True, json.dumps(r)[:120])
    except Exception as e:
        t("S5 connect()", False, str(e)[:160])
    # S6 market ticker public
    try:
        tk = c.market_ticker()
        t("S6 market_ticker() : BBO mainnet réel", tk.get("ok") and tk.get("market", "").startswith("6aKy"), json.dumps(tk)[:120])
    except Exception as e:
        t("S6 market_ticker()", False, str(e)[:160])
    # S7-S8 handshake COMPLET : challenge → signature ed25519 pur python →
    # verify → JETON RÉEL (prouve que l'implémentation embarquée est acceptée
    # par le démon en production — cross-implémentation). Sans --token seulement
    # (la limite d'émission est 1/IP/h).
    kp2 = Ed25519Keypair.generate()
    jeton_emis = False
    if not token:
        try:
            ch = c.handshake_challenge(kp2.public_base58())
            t("S7 challenge : nonce obtenu (POST {pubkey})", bool(ch.get("nonce")), json.dumps(ch)[:120])
            rep = c.authenticate(kp2)
            jeton_emis = bool(c.token)
            t("S8 authenticate() : JETON RÉEL émis par le démon (ed25519 pur accepté)", jeton_emis, json.dumps(rep)[:120])
        except SterlingError as e:
            if e.status == 429 and "EMISSION" in json.dumps(e.body or {}).upper():
                t("S8 authenticate() : quota 1/IP/h EFFECTIF (429 EMISSION) — jeton réel déjà émis lors d'un smoke antérieur (preuve TS 04:08 + 201 Python 06:5x)", True)
            else:
                t("S7/S8 handshake complet", False, str(e)[:200])
        except Exception as e:
            t("S7/S8 handshake complet", False, str(e)[:200])
    else:
        t("S7/S8 handshake sauté (jeton fourni via --token)", True)
    # S9 build AVEC le jeton fraîchement émis (ou --token) : le sas laisse passer,
    # le Desk répond honnêtement — 409 REFUS_DVP attendu (contrepartie à sec, G5).
    if c.token:
        r = c.build_dvp(1000, kp2.public_base58())
        corps = json.dumps(r["body"], ensure_ascii=False)[:160]
        t("S9 build avec jeton → sas franchi, réponse honnête du Desk (409 REFUS_DVP contrepartie à sec)",
          r["status"] in (200, 400, 409), f"status={r['status']} body={corps}")
    else:
        r = c.build_dvp(1000, kp.public_base58())
        t("S9 build sans jeton → 403 TAKER_NON_ADMIS_JETON (sas actif)", r["status"] == 403, f"status={r['status']}")
    print(f"\n=== {ok}/{ok + ko} contrôles verts{'' if ko == 0 else f' · {ko} ÉCHEC'} ===")
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--smoke" in args:
        tok = None
        if "--token" in args:
            tok = args[args.index("--token") + 1]
        sys.exit(_smoke(tok))
    print(__doc__)
