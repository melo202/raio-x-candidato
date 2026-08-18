# ⚡ Raio-X do Candidato

**"Quem é esse candidato, de verdade?"** — em 30 segundos, com fonte oficial em tudo.

O eleitor digita o nome ou número do candidato e recebe uma ficha única, em linguagem
de gente, cruzando fontes oficiais (TSE, TCU, Câmara, Senado) — com link da fonte em
cada dado. **Sem nota, sem ranking, sem selo:** dado + fonte + contexto.

Eleições 2026 · MVP Goiás (888 candidatos) · custo de infra: R$ 0
(GitHub Pages + VPS já existente).

## Princípios inegociáveis

1. **Dado, não nota.** Nunca score, ranking ou selo — é o que protege juridicamente
   e diferencia de agregadores com viés.
2. **Fonte oficial linkada em 100% dos dados.**
3. **Contexto obrigatório em dado sensível** (disclaimer em variação patrimonial,
   aviso de homonímia no cruzamento TCU etc.).
4. **Apartidarismo estrutural:** mesma ficha, mesmos campos, mesma ordem para todos.

## Arquitetura

```
[CSVs TSE + lista TCU + APIs Câmara/Senado]
        │  pipeline Python + cron no VPS
        ▼
[DuckDB]  ← cruzamentos (chave-mestra: CPF entre eleições)
        ▼
[JSONs estáticos: 1 ficha por candidato, shardados por UF]
        │  git commit + push automatizado (cron.sh)
        ▼
[GitHub Pages /docs — vanilla HTML/CSS/JS, PWA, share pro WhatsApp]
        +
[Claude API em batch: resumo neutro de planos de governo]
```

Site 100% estático = aguenta viralizar sem servidor. JSONs shardados por UF
aguentam a escala nacional (~20 mil fichas).

## Rodando

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate

# pipeline completo (download TSE 2014-2026 → DuckDB → fichas → cards → SEO)
python pipeline/run_all.py --ufs GO

# servir localmente
python -m http.server 8080 -d docs   # → http://localhost:8080

# escala nacional: só mudar as UFs
python pipeline/run_all.py --ufs GO SP MG RJ BA ...
```

Módulos individuais: `download.py`, `build_db.py`, `fichas.py`, `sharecards.py`,
`stubs.py` (páginas SEO/OG + sitemap), `radar_noticias.py` (menções na imprensa,
whitelist de veículos), `processos_tse.py` (processos da candidatura — rodar do
VPS, a API do TSE bloqueia IP de datacenter), `resumo_planos.py` (requer
`ANTHROPIC_API_KEY`) e `build_demo.py` (demo auto-contido em 1 HTML).
Tudo aceita `--help`.

Camadas já na ficha: perfil, evolução patrimonial **2014→2026 (7 eleições,
incluindo municipais)** por CPF, **histórico eleitoral completo** (gerais +
municipais: resultados, mandatos exercidos, vezes eleito, trocas de partido com
normalização de fusões/renomeações partidárias), **gestão em números**
(`gestao_numeros.py` — IDEB da rede municipal durante o mandato de ex-prefeitos,
com média estadual de comparação), **doações de campanha que o candidato fez**
(`doacoes_feitas.py` — receitas 2022/2024 cruzadas pelo CPF do doador),
**redes sociais declaradas ao TSE**, TCU (com a lista em `data/tcu/`),
radar de imprensa e processos da candidatura (quando coletados).

### Cron no VPS (situação do registro muda todo dia)

```
30 6 * * * /caminho/raio-x-candidato/pipeline/cron.sh >> /var/log/raiox.log 2>&1
```

### Camada TCU (contas julgadas irregulares)

O portal do TCU bloqueia download automatizado. Exporte a lista em
[contasirregulares.tcu.gov.br](https://contasirregulares.tcu.gov.br) (CSV/XLSX) e
salve em `data/tcu/` — o cruzamento por CPF (primário) e nome (fallback com aviso
de homonímia) entra automaticamente na próxima rodada de `fichas.py`.

## Estrutura das fichas (contrato de dados)

`docs/data/{UF}/{SQ_CANDIDATO}.json` — ficha completa:
perfil, `patrimonio.serie` (2014→2026 por CPF), `patrimonio.variacoes`,
`patrimonio.bens`, `tcu`, e ganchos prontos para as camadas futuras
(`financiamento`, `votacoes`, `mandato`, `processos`, `resumo_plano`).

`docs/data/{UF}/index.json` — índice compacto para busca client-side.

`docs/c/{uf}/{SQ}.html|.png` — página SEO/OG + share card por candidato
(o preview que aparece no WhatsApp; ~20 mil páginas indexáveis na escala nacional).

## Configuração

Tudo em `pipeline/config.py`: `BASE_URL` (troque ao registrar o domínio),
`UFS_ALVO`, anos da série patrimonial, rótulos de situação e disclaimers.

## Publicando no GitHub Pages

Settings → Pages → Deploy from branch → `main` → `/docs`. Com domínio próprio,
adicione o CNAME e atualize `BASE_URL` em `config.py`.

## Roadmap

- [x] Sprint 0 — pipeline TSE 2014→2026, cruzamento patrimonial por CPF, fichas GO
- [x] Sprint 1 — site (busca + ficha + PWA + share card + SEO), camadas 1, 2 e 6
- [ ] Sprint 2 (08–14/09) — camada 3 ao vivo (prestação parcial de contas: 09–13/09)
- [ ] Sprint 3 (15/09–03/10) — escala nacional (27 UFs), monitor diário de registro
- [ ] Pós-eleição — ficha vira acompanhamento de mandato dos eleitos

## Licença e uso dos dados

Código sob MIT. Os dados são públicos, produzidos pelo TSE e demais órgãos citados;
tratamento documentado em [Metodologia](docs/metodologia.html) e base legal LGPD em
[Privacidade](docs/privacidade.html).
