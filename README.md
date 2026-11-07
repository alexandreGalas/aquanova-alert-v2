# Alerte séances Aquanova

Ce petit programme vérifie toutes les 30 minutes les pages de réservation
d'Aquanova America. Dès que le planning d'une nouvelle semaine est mis en ligne,
il envoie un mail court : « Nouveau planning disponible », avec le lien de la semaine.

Il tourne gratuitement sur les serveurs de GitHub : rien à installer sur le
téléphone, et l'ordinateur peut rester éteint.

---

## Mise en route (2 minutes)

### 1. Indiquer à qui envoyer l'alerte

Dans le dépôt : **Settings** → **Secrets and variables** → **Actions** →
onglet **Secrets** → **New repository secret** :

| Nom       | Valeur                                                                 |
|-----------|-------------------------------------------------------------------------|
| `MAIL_TO` | l'adresse qui reçoit les alertes (plusieurs : séparer par des virgules) |

C'est tout : le mail est envoyé par le service gratuit [ntfy.sh](https://ntfy.sh),
sans compte ni mot de passe. L'adresse reste privée (un secret n'est jamais visible,
même dans un dépôt public).

### 2. Tester

1. Onglet **Actions** → si GitHub le demande, cliquer pour activer les workflows.
2. **Surveillance des séances** → **Run workflow** → mode `test` → **Run workflow**.
3. Une minute plus tard, un mail « ✅ Alerte Aquanova : test » arrive, envoyé par ntfy.
   - Pas de mail ? Regarder dans les **spams**, le marquer comme « non spam » et
     ajouter l'expéditeur aux contacts.
   - Une croix rouge dans l'onglet Actions : cliquer dessus pour voir l'erreur.

La vérification tourne ensuite toute seule toutes les 30 minutes.

---

## Option : envoyer depuis un compte Gmail

Plus fiable que ntfy (moins de risque de spam), mais plus long à configurer.

1. Créer une adresse Gmail dédiée, activer la **validation en deux étapes**
   (https://myaccount.google.com/signinoptions/twosv), puis créer un
   **mot de passe d'application** (https://myaccount.google.com/apppasswords).
2. Ajouter deux secrets : `SMTP_USER` (l'adresse Gmail) et `SMTP_PASSWORD`
   (le code de 16 lettres, sans espaces).

Dès que ces deux secrets existent, le programme passe par Gmail au lieu de ntfy.

## Option : surveiller une semaine précise

Le programme lit déjà la semaine en cours et toutes les semaines qu'il trouve en lien.
Pour forcer une semaine : onglet **Variables** → `PERIODES` = le numéro après
`periode=` dans l'adresse de la page (ex. `311502`).

---

## Bon à savoir

- **Quand un mail est envoyé** : quand une semaine passe de « vide » à « au moins une
  séance ». Chaque semaine ne déclenche qu'un seul mail, même si des séances y sont
  ajoutées ensuite. Les semaines déjà publiées au moment de l'installation ne
  déclenchent pas de mail.
- **Si le site change ou tombe en panne** plusieurs heures, un mail « ⚠️ Alerte
  Aquanova en panne » est envoyé une seule fois.
- **Délai** : GitHub peut décaler une vérification de quelques minutes aux heures chargées.
- **Coût** : gratuit.
- **Mettre en pause** : onglet Actions → Surveillance des séances → **⋯** → **Disable workflow**.
- **Changer la fréquence** : dans `.github/workflows/surveillance.yml`, la ligne `cron`.
  Éviter de vérifier plus souvent : le site interdit les robots dans ses conditions
  d'utilisation, donc mieux vaut rester discret et réserver cet outil à un usage personnel.
