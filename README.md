# Alerte séances Aquanova

Ce petit programme vérifie toutes les 30 minutes les pages de réservation
d'Aquanova America. Dès que le planning d'une nouvelle semaine est mis en ligne,
il envoie un mail court : « Nouveau planning disponible », avec le lien de la semaine.

Il tourne gratuitement sur les serveurs de GitHub : rien à installer sur le
téléphone, et l'ordinateur peut rester éteint.

Installation : environ 20 minutes, à faire une seule fois, de préférence sur un ordinateur.

---

## Étape 1 — Préparer un Gmail qui enverra les alertes

Mieux vaut créer une adresse Gmail dédiée (par ex. `alertes.piscine.xxx@gmail.com`)
plutôt que d'utiliser son adresse personnelle.

1. Se connecter à ce compte Gmail.
2. Activer la **validation en deux étapes** : https://myaccount.google.com/signinoptions/twosv
3. Créer un **mot de passe d'application** : https://myaccount.google.com/apppasswords
   - Nom : `Alerte séances`
   - Google affiche un code de 16 lettres. **Le noter** : il ne sera plus affiché.

## Étape 2 — Créer le dépôt GitHub

1. Créer un compte gratuit sur https://github.com
2. En haut à droite : **+** → **New repository**
   - Nom : `alerte-aquanova`
   - Cocher **Private**
   - Cliquer **Create repository**
3. Cliquer **uploading an existing file**, glisser `monitor.py`, `requirements.txt`
   et `README.md`, puis **Commit changes**.
4. Ajouter le fichier d'automatisation (le dossier `.github` est souvent caché sur
   l'ordinateur, donc on le crée à la main) :
   - **Add file** → **Create new file**
   - Nom du fichier, à taper exactement : `.github/workflows/surveillance.yml`
   - Coller le contenu du fichier `surveillance.yml` fourni
   - **Commit changes**

## Étape 3 — Donner les informations du mail

Dans le dépôt : **Settings** → **Secrets and variables** → **Actions**.

Onglet **Secrets** → **New repository secret**, trois fois :

| Nom             | Valeur                                                        |
|-----------------|---------------------------------------------------------------|
| `SMTP_USER`     | l'adresse Gmail de l'étape 1                                  |
| `SMTP_PASSWORD` | le code de 16 lettres (sans espaces)                          |
| `MAIL_TO`       | l'adresse qui reçoit les alertes (plusieurs : séparer par des virgules) |

Onglet **Variables** (facultatif) → **New repository variable** :

| Nom        | À quoi ça sert                                                         | Exemple              |
|------------|-------------------------------------------------------------------------|----------------------|
| `PERIODES` | Semaines précises à surveiller (le numéro après `periode=` dans l'adresse) | `311502`             |

Le programme lit déjà la semaine en cours et toutes les semaines qu'il trouve en
lien. `PERIODES` sert à s'assurer qu'une semaine précise est bien surveillée.

## Étape 4 — Tester

1. Onglet **Actions** → si GitHub le demande, cliquer pour activer les workflows.
2. Cliquer **Surveillance des séances** → **Run workflow** → mode `test` → **Run workflow**.
3. Une minute plus tard, un mail « ✅ Alerte Aquanova : test » arrive.
   - Pas de mail ? Regarder dans les **spams** et marquer le mail comme « non spam ».
   - Une croix rouge dans l'onglet Actions : cliquer dessus pour voir l'erreur.
     Le plus souvent, c'est un secret mal recopié.

C'est terminé : la vérification tourne ensuite toute seule toutes les 30 minutes.

---

## Bon à savoir

- **Quand un mail est envoyé** : quand une semaine passe de « vide » à « au moins une
  séance ». Chaque semaine ne déclenche qu'un seul mail, même si des séances y sont
  ajoutées ensuite. Les semaines déjà publiées au moment de l'installation ne
  déclenchent pas de mail.
- **Si le site change ou tombe en panne** plusieurs heures, un mail « ⚠️ la surveillance
  ne fonctionne plus » est envoyé une seule fois.
- **Délai** : GitHub peut décaler une vérification de quelques minutes aux heures chargées.
- **Coût** : gratuit. Une vérification toutes les 30 minutes reste dans le quota offert
  par GitHub pour les dépôts privés.
- **Mettre en pause** : onglet Actions → Surveillance des séances → **⋯** → **Disable workflow**.
- **Changer la fréquence** : dans `surveillance.yml`, la ligne `cron`. Éviter de vérifier
  plus souvent : le site interdit les robots dans ses conditions d'utilisation, donc
  mieux vaut rester discret et réserver cet outil à un usage personnel.
