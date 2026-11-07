# Alerte séances Aquanova

Ce petit programme vérifie toutes les 30 minutes les pages de réservation
d'Aquanova America. Dès que le planning d'une nouvelle semaine est mis en ligne,
il envoie une **notification sur le téléphone** : « Nouveau planning disponible ».
Toucher la notification ouvre la page de réservation de la semaine.

Il tourne gratuitement sur les serveurs de GitHub : l'ordinateur peut rester éteint.

---

## Sur le téléphone (1 minute)

1. Installer l'app gratuite **ntfy** (App Store ou Google Play).
2. Toucher **+** (« S'abonner à un sujet »), garder le serveur `ntfy.sh` et taper
   le nom du canal (communiqué à l'installation, de la forme `aquanova-xxxxxxxx…`).
3. Autoriser les notifications quand l'app le demande.

Aucun compte n'est nécessaire.

## Sur GitHub

Le nom du canal est calculé à partir du secret `MAIL_TO` (onglet **Settings** →
**Secrets and variables** → **Actions**). On peut aussi le choisir soi-même avec un
secret `NTFY_TOPIC` : un nom long et difficile à deviner, car toute personne qui le
connaît peut s'y abonner.

### Tester

**Actions** → **Surveillance des séances** → **Run workflow** → mode `test`.
Une notification « ✅ Alerte Aquanova : test » arrive dans l'app ntfy.

---

## Option : recevoir aussi un mail (Gmail)

Si les secrets `SMTP_USER` (adresse Gmail) et `SMTP_PASSWORD` (mot de passe
d'application de 16 lettres, https://myaccount.google.com/apppasswords) existent, un
mail est envoyé à `MAIL_TO` en plus de la notification. S'il échoue, la notification
part quand même.

## Option : surveiller une semaine précise

Le programme lit déjà la semaine en cours et toutes les semaines qu'il trouve en lien.
Pour forcer une semaine : onglet **Variables** → `PERIODES` = le numéro après
`periode=` dans l'adresse de la page (ex. `311502`).

---

## Bon à savoir

- **Quand une alerte est envoyée** : quand une semaine atteint 20 séances (quelques
  activités bien-être sont souvent publiées en avance ; le vrai planning en compte 60 à 70).
  Le seuil se change avec la variable `SEUIL_PLANNING`. Chaque semaine ne déclenche qu'une seule alerte, même si des séances y sont
  ajoutées ensuite. Les semaines déjà publiées au moment de l'installation ne
  déclenchent pas d'alerte.
- **Si le site change ou tombe en panne** plusieurs heures, une alerte « ⚠️ Alerte
  Aquanova en panne » est envoyée une seule fois.
- **Délai** : GitHub peut décaler une vérification de quelques minutes aux heures chargées.
- **Coût** : gratuit.
- **Mettre en pause** : onglet Actions → Surveillance des séances → **⋯** → **Disable workflow**.
- **Changer la fréquence** : dans `.github/workflows/surveillance.yml`, la ligne `cron`.
  Éviter de vérifier plus souvent : le site interdit les robots dans ses conditions
  d'utilisation, donc mieux vaut rester discret et réserver cet outil à un usage personnel.
