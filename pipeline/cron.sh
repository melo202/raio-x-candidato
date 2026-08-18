#!/usr/bin/env bash
# Cron diário no VPS (padrão SwissTony): re-baixa dados de 2026, recomputa
# as fichas e publica no GitHub Pages via commit dos JSONs.
#
# Instalação no VPS:
#   crontab -e
#   30 6 * * * /caminho/raio-x-candidato/pipeline/cron.sh >> /var/log/raiox.log 2>&1
#
# (situação do registro — deferido/indeferido/sub judice — muda todo dia até a eleição)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# venv do projeto (crie uma vez: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

echo "== $(date -Iseconds) raio-x cron start =="
"$PY" pipeline/run_all.py --force

git add docs/data docs/c docs/sitemap*.xml docs/robots.txt docs/sw.js
if git diff --cached --quiet; then
  echo "sem mudanças — nada a publicar"
else
  git commit -m "dados: atualização automática $(date +%F)"
  git push origin main
  echo "publicado"
fi
echo "== $(date -Iseconds) raio-x cron end =="
