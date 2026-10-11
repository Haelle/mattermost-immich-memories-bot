# mattermost-immich-memories-bot

Bot Mattermost qui envoie chaque jour, en conversation privée, les souvenirs Immich « ce jour-là » de chaque utilisateur inscrit, avec un lien `immich://` par souvenir et sa photo de couverture.

Chaque utilisateur s'inscrit seul avec `/souvenirs activer` et sa propre clé API Immich (lecture seule), saisie dans une boîte de dialogue : la clé ne transite jamais par un message.

## Commandes

| Commande | Effet |
| --- | --- |
| `/souvenirs activer` | Ouvre la boîte de dialogue ; inscrit l'utilisateur ou remplace sa clé |
| `/souvenirs statut` | Actif ou non, heure d'envoi, date d'inscription, dernier envoi, dernière erreur |
| `/souvenirs heure HH:MM` | Change l'heure d'envoi quotidienne ; sans argument, l'affiche |
| `/souvenirs test` | Envoie tout de suite le message du jour |
| `/souvenirs désactiver` | Supprime la clé et l'inscription |

## Mise en place

### Mattermost

1. *Console système → Intégrations → Gestion des intégrations* : activer les commandes slash et les comptes bot.
2. *Console système → Configuration du site → Publications → Schémas d'URL personnalisés* : ajouter `immich`. Sans ce réglage, les liens `immich://` ne sont pas cliquables.
3. *Intégrations → Comptes bot* : créer le bot `souvenirs` (rôle Membre) et conserver son jeton.
4. *Intégrations → Commandes slash* : créer `/souvenirs`, URL `https://souvenirs.example.com/command`, méthode POST, autocomplétion `[activer | statut | heure | test | désactiver]`. Conserver le jeton. La commande est liée à une équipe : la créer dans chaque équipe concernée.

### Déploiement

```yaml
services:
  souvenirs:
    image: estb/mattermost-immich-memories-bot:latest
    restart: unless-stopped
    environment:
      IMMICH_URL: https://photos.example.com
      MM_URL: https://mm.example.com
      PUBLIC_CALLBACK_URL: https://souvenirs.example.com
      TZ: Europe/Paris
      CHECK_INTERVAL_MINUTES: "60"
      MM_BOT_TOKEN: change-me
      MM_COMMAND_TOKENS: team-a-token,team-b-token
      MASTER_KEY: change-me
    volumes:
      - souvenirs-data:/data
    ports:
      - "127.0.0.1:8000:8000"

volumes:
  souvenirs-data:
```

Les valeurs sont des exemples : adapter les URL et fournir les secrets (`MM_BOT_TOKEN`, `MM_COMMAND_TOKENS`, `MASTER_KEY`) depuis un `.env` plutôt qu'en clair. Mattermost doit joindre le service à `PUBLIC_CALLBACK_URL` : le publier derrière un reverse proxy HTTPS, car le jeton de la commande et la clé Immich saisie dans la boîte de dialogue transitent dans ces requêtes. Si cette adresse est une IP privée, l'ajouter dans *Console système → Environnement → Développeur → Autoriser les connexions internes non fiables vers*. Pour générer `MASTER_KEY` :

```sh
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

Puis `docker compose up -d`, et vérifier avec son propre compte : `/souvenirs activer`, puis `/souvenirs test`.

**Sauvegarder `MASTER_KEY`** : sans elle, les clés stockées sont illisibles et chaque utilisateur doit relancer `/souvenirs activer`.

### Clé API Immich (côté utilisateur)

*Paramètres du compte → Clés API* : créer une clé avec uniquement la lecture des souvenirs (`memory.read`) et des photos (`asset.view`). Noms à confirmer selon la version d'Immich.

## Configuration

Chaque variable peut aussi être lue depuis un fichier via `<NOM>_FILE`.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `IMMICH_URL` | requis | URL d'Immich |
| `MM_URL` | requis | URL de Mattermost |
| `MM_BOT_TOKEN` | requis | Jeton du compte bot |
| `MM_COMMAND_TOKENS` | requis | Jetons de la commande slash, séparés par des virgules (un par équipe) |
| `MASTER_KEY` | requis | Clé Fernet de chiffrement des clés Immich |
| `PUBLIC_CALLBACK_URL` | requis | Adresse publique du service, vue par Mattermost (`https://souvenirs.example.com`) |
| `CHECK_INTERVAL_MINUTES` | `60` | Intervalle entre deux passages d'envoi ; diviseur de 60 (1, 5, 15, 30, 60) |
| `TZ` | `Europe/Paris` | Fuseau qui définit « aujourd'hui » et les heures d'envoi |
| `DB_PATH` | `/data/souvenirs.db` | Base SQLite, sur un volume |
| `LINK_TEMPLATE` | `immich://memory?id={id}` | Modèle de lien vers un souvenir |

Chaque utilisateur choisit son heure d'envoi dans la boîte de dialogue d'activation (09:00 proposé), puis avec `/souvenirs heure`. Les envois se calent sur les multiples de l'intervalle depuis minuit : avec 60 minutes, une heure réglée à 08:30 part à 09:00. Un passage manqué (conteneur arrêté) n'est pas rattrapé.

## Développement

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run pyright
docker build -t mattermost-immich-memories-bot .
```

## Publication

La CI GitHub Actions lance le lint, le typage, les tests et la construction de l'image (amd64 et arm64) sur chaque pull request. Elle publie l'image sur Docker Hub ([`estb/mattermost-immich-memories-bot`](https://hub.docker.com/r/estb/mattermost-immich-memories-bot)) :

- à chaque push sur `master` : tag `dev` ;
- à chaque tag git `X.Y.Z` (ou `vX.Y.Z`) : tags `X.Y.Z`, `X.Y`, `X` et `latest`.

Secrets GitHub requis : `DOCKERHUB_USERNAME` et `DOCKERHUB_ACCESS_TOKEN`.
