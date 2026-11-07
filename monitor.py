"""Surveille les pages de réservation d'Aquanova America et envoie un mail
quand le planning d'une nouvelle semaine est mis en ligne.

Configuration par variables d'environnement (voir README.md) :
  MAIL_TO     -> obligatoire : adresse(s) qui reçoivent l'alerte
  SMTP_USER, SMTP_PASSWORD -> facultatifs : si renseignés, le mail part de ce compte
                 Gmail ; sinon il est envoyé par le service gratuit ntfy.sh
  PERIODES    -> identifiants de semaines à surveiller, séparés par des virgules (optionnel)
  MODE        -> "normal" (défaut) ou "test" (envoie tout de suite un mail de test)

Règle anti-doublon : une semaine est identifiée par son intitulé
(« Du 30 novembre au 6 décembre 2026 »). Dès qu'elle contient au moins une séance,
un mail est envoyé et la semaine est notée dans etat.json : elle ne déclenchera
plus jamais de mail, même si des séances y sont ajoutées ensuite.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import sys
import time
from datetime import date, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SITE = "https://aquanova-america.fr"
PAGE_RESERVER = f"{SITE}/module-inscriptions/reserver/"
FICHIER_ETAT = Path(os.environ.get("STATE_FILE", "etat.json"))

MAX_PAGES = 10          # nombre maximum de semaines lues à chaque vérification
PAUSE_ENTRE_PAGES = 2   # secondes, pour ne pas charger le site
JOURS_DE_MEMOIRE = 90   # on oublie les semaines signalées il y a plus de 90 jours
ECHECS_AVANT_ALERTE = 6 # 6 vérifications ratées d'affilée (~3 h) avant de prévenir

ENTETES = {
    "User-Agent": "Mozilla/5.0 (compatible; alerte-seances-perso/1.0)",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

RE_JOUR = re.compile(r"^(LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE)\s+\d{1,2}/\d{1,2}")
RE_SEMAINE = re.compile(r"Du\s+\d{1,2}(?:\s+\w+)?(?:\s+\d{4})?\s+au\s+\d{1,2}\s+\w+\s+\d{4}")
# Identifiants de semaines cités dans la page : liens "periode=…" et flèches
# « semaine suivante » du type onclick='update_link_periodes(341055)'.
RE_PERIODE = re.compile(r"periode[\"'=:\s]+[\"']?(\d{4,9})|update_link_periodes\(\s*['\"]?(\d{4,9})")


class ErreurStructure(Exception):
    """La page ne ressemble plus à ce que le script attend (site modifié)."""


# --------------------------------------------------------------------------- lecture

def url_periode(periode: str | None) -> str:
    return f"{PAGE_RESERVER}?periode={periode}" if periode else PAGE_RESERVER


def telecharger(url: str) -> str:
    reponse = requests.get(url, headers=ENTETES, timeout=30)
    reponse.raise_for_status()
    return reponse.text


def analyser_page(html: str) -> dict:
    """Renvoie l'intitulé de la semaine, son nombre de séances et les autres semaines citées."""
    soup = BeautifulSoup(html, "html.parser")

    m = RE_SEMAINE.search(soup.get_text(" ", strip=True))
    if not m:
        raise ErreurStructure("intitulé de semaine (« Du … au … ») introuvable")
    semaine = " ".join(m.group(0).split())

    nb_seances, jours_vus, dans_un_jour = 0, 0, False
    for titre in soup.find_all(["h2", "h3"]):
        texte = titre.get_text(" ", strip=True)
        if titre.name == "h2":
            dans_un_jour = bool(RE_JOUR.match(texte.upper()))
            jours_vus += dans_un_jour
        elif dans_un_jour and texte:
            nb_seances += 1

    if jours_vus == 0:
        raise ErreurStructure("aucun jour (LUNDI, MARDI…) trouvé sur la page")

    return {"semaine": semaine, "nb_seances": nb_seances, "periodes": {a or b for a, b in RE_PERIODE.findall(html)}}


def collecter(periodes_config: list[str]) -> list[dict]:
    """Lit la semaine en cours, les semaines configurées et celles découvertes en chemin."""
    a_lire: list[str | None] = [None] + periodes_config
    vues: set[str | None] = set()
    pages = []
    while a_lire and len(pages) < MAX_PAGES:
        periode = a_lire.pop(0)
        if periode in vues:
            continue
        vues.add(periode)
        if pages:
            time.sleep(PAUSE_ENTRE_PAGES)
        url = url_periode(periode)
        page = analyser_page(telecharger(url))
        page["url"] = url
        pages.append(page)
        a_lire += sorted(p for p in page["periodes"] if p not in vues)
    return pages


# --------------------------------------------------------------------------- état

def charger_etat() -> dict | None:
    if not FICHIER_ETAT.exists():
        return None
    etat = json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
    return etat if "semaines" in etat else None  # ancien format -> on repart de zéro


def sauver_etat(etat: dict) -> None:
    FICHIER_ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")


# --------------------------------------------------------------------------- mail

def destinataires() -> list[str]:
    return [d.strip() for d in os.environ.get("MAIL_TO", "").split(",") if d.strip()]


def envoyer_mail(sujet: str, texte: str, html: str, lien: str) -> None:
    if not destinataires():
        raise SystemExit("Secret MAIL_TO manquant : impossible d'envoyer l'alerte.")
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        envoyer_par_smtp(sujet, texte, html)
    else:
        envoyer_par_ntfy(sujet, texte, lien)


def envoyer_par_ntfy(sujet: str, texte: str, lien: str) -> None:
    """Fait envoyer le mail par ntfy.sh : aucun compte ni mot de passe nécessaire.
    Le nom du canal ntfy est dérivé de l'adresse, pour rester impossible à deviner."""
    serveur = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    for adresse in destinataires():
        canal = "aquanova-" + hashlib.sha256(adresse.lower().encode()).hexdigest()[:20]
        reponse = requests.post(serveur, timeout=30, json={
            "topic": canal, "title": sujet, "message": texte, "click": lien, "email": adresse,
        })
        if reponse.status_code >= 400:
            raise RuntimeError(f"ntfy a refusé l'envoi ({reponse.status_code}) : {reponse.text.strip()}")
        print("Mail envoyé via ntfy.sh.")


def envoyer_par_smtp(sujet: str, texte: str, html: str) -> None:
    utilisateur = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = f"Alerte Aquanova <{utilisateur}>"
    msg["To"] = ", ".join(destinataires())
    msg.set_content(texte)
    msg.add_alternative(html, subtype="html")
    hote = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(hote, port, timeout=30) as serveur:
        serveur.login(utilisateur, os.environ["SMTP_PASSWORD"])
        serveur.send_message(msg)


def mail_simple(sujet: str, lignes: list[tuple[str, str]]) -> None:
    """lignes = [(texte, lien), …]"""
    texte = "\n".join(f"{t}\n{l}" for t, l in lignes)
    html = "".join(f"<p style='font-family:Arial,sans-serif;font-size:15px'>"
                   f"<a href='{escape(l)}'>{escape(t)}</a></p>" for t, l in lignes)
    envoyer_mail(sujet, texte, html, lignes[0][1])


# --------------------------------------------------------------------------- principal

def main() -> int:
    mode = os.environ.get("MODE", "normal").strip().lower() or "normal"
    periodes_config = [p.strip() for p in os.environ.get("PERIODES", "").split(",") if p.strip()]

    etat_existant = charger_etat()
    etat = etat_existant or {"semaines": {}, "echecs": 0, "alerte_erreur": False}
    aujourdhui = date.today().isoformat()

    try:
        pages = collecter(periodes_config)
    except (requests.RequestException, ErreurStructure) as e:
        etat["echecs"] = etat.get("echecs", 0) + 1
        print(f"Échec de la vérification ({etat['echecs']} d'affilée) : {e}")
        if etat["echecs"] >= ECHECS_AVANT_ALERTE and not etat.get("alerte_erreur"):
            mail_simple("⚠️ Alerte Aquanova en panne",
                        [(f"La surveillance ne fonctionne plus depuis quelques heures ({e}).", PAGE_RESERVER)])
            etat["alerte_erreur"] = True
        sauver_etat(etat)
        return 0

    etat["echecs"] = 0
    etat["alerte_erreur"] = False

    nouvelles = []
    for page in pages:
        print(f"{page['semaine']} : {page['nb_seances']} séance(s)")
        if page["nb_seances"] > 0 and page["semaine"] not in etat["semaines"]:
            etat["semaines"][page["semaine"]] = aujourdhui
            nouvelles.append(page)

    limite = (date.today() - timedelta(days=JOURS_DE_MEMOIRE)).isoformat()
    etat["semaines"] = {s: d for s, d in etat["semaines"].items() if d >= limite}

    if mode == "test":
        mail_simple("✅ Alerte Aquanova : test", [("Test réussi, la surveillance fonctionne.", PAGE_RESERVER)])
    elif etat_existant is None:
        print("Première vérification : plannings actuels mémorisés, pas de mail.")
    elif nouvelles:
        mail_simple("🏊 Nouveau planning disponible à Aquanova",
                    [(f"Semaine {p['semaine'][0].lower()}{p['semaine'][1:]}", p["url"]) for p in nouvelles])

    sauver_etat(etat)
    return 0


if __name__ == "__main__":
    sys.exit(main())
