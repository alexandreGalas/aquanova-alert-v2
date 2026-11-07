"""Surveille les pages de réservation d'Aquanova America et envoie une alerte
quand le planning d'une nouvelle semaine est mis en ligne.

L'alerte est une notification push envoyée par ntfy.sh (app gratuite ntfy).

Configuration par variables d'environnement (voir README.md) :
  NTFY_TOPIC  -> nom du canal ntfy (facultatif : sinon dérivé de MAIL_TO)
  MAIL_TO, SMTP_USER, SMTP_PASSWORD -> facultatifs : envoi d'un mail en plus via Gmail
  PERIODES    -> identifiants de semaines à surveiller, séparés par des virgules (optionnel)
  MODE        -> "normal" (défaut) ou "test" (envoie tout de suite un mail de test)

Règle anti-doublon : une semaine est identifiée par son intitulé
(« Du 30 novembre au 6 décembre 2026 »). Dès qu'elle contient au moins SEUIL_PLANNING
séances (quelques activités bien-être sont souvent publiées en avance, le vrai
planning en compte 60 à 70),
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
SEUIL_PLANNING = int(os.environ.get("SEUIL_PLANNING") or 20)  # séances pour dire « planning publié »
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


def lire_page(url: str, essais: int = 3) -> dict:
    """Télécharge et analyse une page, en réessayant si le site renvoie une page inattendue."""
    for essai in range(1, essais + 1):
        html = telecharger(url)
        try:
            return analyser_page(html)
        except ErreurStructure as e:
            titre = BeautifulSoup(html, "html.parser").title
            apercu = " ".join(BeautifulSoup(html, "html.parser").get_text(" ", strip=True).split())[:200]
            print(f"Page inattendue (essai {essai}/{essais}) {url} : {len(html)} caractères, "
                  f"titre « {titre.get_text(strip=True) if titre else '-'} », début : {apercu}")
            if essai == essais:
                raise e
            time.sleep(10 * essai)


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
        page = lire_page(url)
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


def canal_ntfy() -> str:
    """Nom du canal ntfy : secret NTFY_TOPIC, sinon dérivé de MAIL_TO (impossible à deviner)."""
    if os.environ.get("NTFY_TOPIC", "").strip():
        return os.environ["NTFY_TOPIC"].strip()
    if destinataires():
        return "aquanova-" + hashlib.sha256(destinataires()[0].lower().encode()).hexdigest()[:20]
    raise SystemExit("Ni NTFY_TOPIC ni MAIL_TO : impossible de savoir où envoyer l'alerte.")


def envoyer_mail(sujet: str, texte: str, html: str, lien: str) -> None:
    """Envoie l'alerte en notification push (app ntfy), et aussi par mail si Gmail est configuré."""
    envoyer_par_ntfy(sujet, texte, lien)
    if destinataires() and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        try:
            envoyer_par_smtp(sujet, texte, html)
        except Exception as e:  # le mail est un bonus : la notification est déjà partie
            print(f"Mail Gmail non envoyé (la notification push, elle, est partie) : {e}")


def envoyer_par_ntfy(sujet: str, texte: str, lien: str) -> None:
    """Notification push via ntfy.sh : aucun compte ni mot de passe nécessaire."""
    serveur = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    reponse = requests.post(serveur, timeout=30, json={
        "topic": canal_ntfy(), "title": sujet, "message": texte, "click": lien,
        "tags": ["swimmer"], "priority": 4,
    })
    if reponse.status_code >= 400:
        raise RuntimeError(f"ntfy a refusé l'envoi ({reponse.status_code}) : {reponse.text.strip()}")
    print("Notification envoyée via ntfy.sh.")


def envoyer_par_smtp(sujet: str, texte: str, html: str) -> None:
    utilisateur = os.environ["SMTP_USER"].strip()
    # Un mot de passe d'application est souvent copié avec des espaces ("abcd efgh ijkl mnop").
    mot_de_passe = "".join(os.environ["SMTP_PASSWORD"].split())
    if not re.fullmatch(r"[a-zA-Z]{16}", mot_de_passe):
        print(f"Attention : SMTP_PASSWORD fait {len(mot_de_passe)} caractères ; un mot de passe "
              "d'application Gmail fait 16 lettres. Vérifier qu'il ne s'agit pas du mot de passe du compte.")
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = f"Alerte Aquanova <{utilisateur}>"
    msg["To"] = ", ".join(destinataires())
    msg.set_content(texte)
    msg.add_alternative(html, subtype="html")
    hote = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    derniere_erreur: Exception | None = None
    for port in (465, 587):  # SSL direct, puis STARTTLS
        try:
            if port == 465:
                serveur = smtplib.SMTP_SSL(hote, port, timeout=30)
            else:
                serveur = smtplib.SMTP(hote, port, timeout=30)
                serveur.starttls()
            with serveur:
                serveur.login(utilisateur, mot_de_passe)
                serveur.send_message(msg)
            print(f"Mail envoyé via Gmail (port {port}).")
            return
        except smtplib.SMTPAuthenticationError as e:
            raise RuntimeError(
                "Gmail refuse l'identifiant ou le mot de passe. SMTP_USER doit être l'adresse Gmail "
                "complète et SMTP_PASSWORD le mot de passe d'application de 16 lettres "
                f"(https://myaccount.google.com/apppasswords). Réponse de Gmail : {e.smtp_error!r}"
            ) from e
        except (smtplib.SMTPException, OSError) as e:
            print(f"Échec de connexion à Gmail sur le port {port} : {e!r}")
            derniere_erreur = e
    raise RuntimeError(
        "Gmail a coupé la connexion. Causes probables : mot de passe d'application incorrect, "
        "ou connexion bloquée par Google (regarder dans la boîte du compte d'envoi s'il y a une "
        "alerte de sécurité et confirmer que c'est bien toi)."
    ) from derniere_erreur


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
        if mode == "test":
            raise
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
        if page["nb_seances"] >= SEUIL_PLANNING and page["semaine"] not in etat["semaines"]:
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
