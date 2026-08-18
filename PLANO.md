# RAIO-X DO CANDIDATO — Plano Mestre e Status
### "Quem é esse candidato, de verdade?" — em 30 segundos, com fonte oficial em tudo.

**Autor:** Bruno Melo de Carvalho · **Eleição:** 04/10/2026 · **Última atualização:** 18/08/2026 (noite)
**Este arquivo é o ponto de retomada.** Nova sessão de trabalho? Comece lendo isto,
depois `README.md` (como rodar) e `FONTES-DE-DADOS.md` (mapa de fontes + jurídico).

---

## Como retomar o trabalho numa nova sessão com o Claude

1. Abra o app desktop do Claude com a pasta do projeto autorizada
   (`C:\Users\bruno\Documents\Projeto Raio X do Candidato`) **ou** anexe o zip do repo.
2. Diga: *"Continua o Raio-X do Candidato — lê o PLANO.md e me diz o próximo passo."*
3. Os dados brutos (data/raw/, ~4GB + ~2GB RFB) NÃO vão no zip — o pipeline re-baixa
   tudo do TSE com `python pipeline/run_all.py --ufs GO` (~15 min) e da Receita com
   `python pipeline/qsa.py --baixar`. O que importa está no código.

## Princípios inegociáveis (não mudar nunca)

1. **Dado, não nota.** Zero score, ranking, selo ou adjetivo. Fato + fonte + contexto.
2. **Fonte oficial linkada em 100% dos dados.**
3. **Contexto obrigatório em dado sensível** (disclaimers fixos no pipeline).
4. **Apartidarismo estrutural:** mesma ficha, mesmos campos, mesma ordem pra todos.
5. Nunca escrever "fraude"/"escândalo": só registro oficial com processo e órgão.

---

## STATUS — o que JÁ ESTÁ PRONTO (18/08/2026, sessão da noite)

**Pipeline completo + site funcionando com dados reais de GO (888 candidatos).**
Testado ponta a ponta, com validação independente contra os CSVs brutos.

| Camada | Estado | Módulo |
|---|---|---|
| Ficha básica + situação do registro | ✅ rodando | `fichas.py` |
| Patrimônio 2014→2026 (7 eleições, por CPF) | ✅ rodando | `build_db.py` |
| Histórico eleitoral (gerais + municipais, mandatos, trocas de partido c/ linhagem) | ✅ rodando | `fichas.py` |
| Gestão em números (IDEB do município no mandato, 40 ex-gestores GO) | ✅ rodando | `gestao_numeros.py` |
| **Finanças do município no mandato (Siconfi/DCA: receita, despesa, investimento — per capita, IPCA)** | ✅ **NOVO 18/08** — 40 ex-gestores GO | `siconfi.py` |
| **TCM-GO: contas c/ parecer pela rejeição ou julgadas irregulares (1.382 registros, API REST)** | ✅ **NOVO 18/08** — 5 candidatos GO, 9 registros, dupla coincidência validada | `tcmgo.py` |
| **QSA/Receita: participações societárias × sanções (23.243 vínculos BR, 451 candidatos GO; 16.052 PJs cruzadas)** | ✅ **NOVO 18/08** — dupla coincidência (nome + 6 dígitos centrais) | `qsa.py` |
| Doações que o candidato FEZ (receitas 2022/2024 por CPF doador) | ✅ rodando | `doacoes_feitas.py` |
| Sanções CGU: CEIS/CNEP/CEAF (34 hits nacionais, 1 GO) | ✅ rodando | `sancoes.py` |
| Atuação parlamentar (18 dep. federais GO: projetos, leis, votações, CEAP) | ✅ rodando | `parlamentar.py` |
| Redes sociais declaradas ao TSE | ✅ rodando | `build_db.py` |
| Radar de imprensa (whitelist, 17 majoritários GO) | ✅ rodando | `radar_noticias.py` |
| Share cards OG + 888 páginas SEO + sitemap | ✅ rodando | `sharecards.py`, `stubs.py` |
| Site (busca, ficha, PWA, share WhatsApp, Metodologia, LGPD) — **agora com as 4 seções novas** | ✅ pronto | `docs/` |
| Injeção de camadas nas fichas SEM rebuild do banco | ✅ **NOVO 18/08** | `injetar.py` |
| CNIA/CNJ improbidade | ⚙️ módulo drop-in pronto; **captcha server-side ⇒ VPS NÃO resolve** — coleta via Chrome assistido ou CSV manual em `data/cnia/` | `cnia.py` |
| TCM-GO contas irregulares/rejeitadas (municipal) | ✅ rodando (5 candidatos, 9 registros) | `tcmgo.py` |
| TCE-GO contas julgadas irregulares (estadual) | ✅ rodando (2 candidatos, por CPF completo) | `tcego.py` |
| Siconfi — finanças municipais no mandato (DCA, per capita, IPCA) | ✅ rodando (40 ex-gestores) | `siconfi.py` |
| QSA/Receita — empresas dos candidatos × sanções PJ | ✅ rodando (451 candidatos GO; 23.243 vínculos BR) | `qsa.py` |
| CNIA/CNJ improbidade | ⚙️ módulo drop-in pronto; captcha server-side bloqueia automação (VPS NÃO resolve) — coleta via Chrome assistido ou manual | `cnia.py` |
| ALEGO — atuação de dep. estaduais (proposições, leis, frequência) | ✅ rodando (44 candidatos; coleta assistida via Chrome, dump 18/08) | `alego.py` |
| Dep. federais — como votou (15 matérias maior quórum) + emendas por destino | ✅ rodando (18 candidatos) | `parlamentar.py`, `emendas.py` |
| Quem financia 2026 (receitas, doadores, fornecedores × CEIS/CNEP) | ⚙️ pronto e encadeado; ativa sozinho quando o TSE publicar a parcial (09-13/09) | `financiamento.py` |
| PRESIDENTE (circunscrição BR): 26 fichas + chip na busca + sitemap | ✅ rodando (pipeline completo rodou no container — ensaio de escala ok) | `fichas.py --ufs BR` |
| TCU contas irregulares | ⚙️ cruzador pronto; falta o CSV manual em `data/tcu/` (portal tem WAF) | `tcu.py` |
| Processos da candidatura (API DivulgaCand) | ⚙️ módulo pronto; RODAR DO VPS (bloqueia datacenter) | `processos_tse.py` |
| Resumo IA de planos de governo | ⚙️ pronto; precisa `ANTHROPIC_API_KEY` | `resumo_planos.py` |

## DESCOBERTAS 18/08 (sessão Claude)

- CNIA: bloqueio é reCAPTCHA validado no servidor, não IP → VPS não resolve. Módulo
  drop-in pronto (`data/cnia/*.csv`); caminho: Chrome assistido ou consulta dirigida.
- TCE-GO: painel Qlik é só índice; dados = PDFs por eleição com CPF COMPLETO
  (`portal.tce.go.gov.br/contas-irregulares`). 2026: 37 responsáveis. Já cruzado.
- Receita/CNPJ: dadosabertos.rfb.gov.br morreu → Nextcloud WebDAV público
  (share YggdBLfdninEJX9 em arquivos.receitafederal.gov.br, ver `qsa.py`).
- `injetar.py` novo: injeta camadas nas fichas publicadas sem re-rodar fichas.py.
- Sidecars novos em docs/data/: tcmgo/, tcego/, siconfi/, qsa/ (+ cnia/ quando houver).
- data/raiox.duckdb daqui é PARCIAL (cand_2026, sancoes_*, qsa_candidatos) — o banco
  completo continua sendo o do seu ambiente local/VPS.

## AUDITORIA 18/08 — ver AUDITORIA.md

4 frentes (código, dados, front, jurídico). Dados validados sem divergência (Siconfi ao
centavo, QSA no bruto da RFB, patrimônio 638/638). 17 correções aplicadas no mesmo dia —
destaques: filtro LGPD nas descrições de bens (90 fichas limpas), fallback por nome do TCU
restrito, higiene de sidecars (quem sai da lista sai da ficha), run_all encadeando as 10
camadas, sw.js versionado, tabelas mobile, "nada consta" com escopo+data, metodologia v2.0,
privacidade com base legal correta + responsável identificado, docs/c gerado (888 stubs).
Backlog priorizado no AUDITORIA.md.

## PENDENTE — ações do Bruno (destravam o resto)

- [ ] **Publicar:** criar repo GitHub → push → Settings/Pages → branch main, pasta `/docs`.
      Depois atualizar `BASE_URL` em `pipeline/config.py` (e registrar domínio .com.br).
- [ ] **Cron no VPS:** `30 6 * * * /caminho/raio-x-candidato/pipeline/cron.sh` (situação
      do registro muda todo dia). Adicionar `tcmgo.py` + `injetar.py` ao cron (lista TCM muda).
- [ ] **CNIA via Chrome:** sessão com Claude in Chrome na sua máquina — lote dirigido
      (~60 nomes: majoritários + ex-gestores), resultado vira CSV em `data/cnia/`.
- [ ] Baixar lista TCU (contasirregulares.tcu.gov.br) → soltar em `data/tcu/`.
- [ ] Rodar `processos_tse.py` do VPS (esse sim é bloqueio de IP).
- [ ] Decidir nome definitivo + domínio.

## ROADMAP — próximas camadas (ordem de valor, ver FONTES-DE-DADOS.md)

1. **CNIA/CNJ — coleta assistida** (ver PENDENTE; módulo pronto).
2. **TCM-GO fase 2 — pareceres ano a ano (aprovações incluídas)** via widget JSF ou LAI.
3. **Comparador lado a lado de 2-3 candidatos** (feature de UX nº 1 pro eleitor indeciso).
4. **Camada 3 — quem financia 2026:** prestação parcial cai no TSE em **09-13/09** →
   gancho de lançamento pra imprensa. Fornecedores × `sancoes_pj` × QSA (já materializados).
5. Senado (API) para senadores candidatos; ALEGO (scraping) pros 587 estaduais.
6. Emendas por município × base eleitoral (`votacao_candidato_munzona`).

## CALENDÁRIO CRÍTICO

- **09-13/09:** prestação parcial de contas → lançar camada "quem financia" + pauta imprensa.
- **15/09→:** escala nacional (mesmo pipeline, `--ufs` com as 27; ~20 mil fichas/páginas SEO).
  O QSA já está casado para o Brasil inteiro (23.243 vínculos na tabela `qsa_candidatos`).
- **04/10:** 1º turno · **25/10:** 2º turno (segundo pico).
- **Pós-eleição:** ficha vira acompanhamento de mandato; base vira produto B2B.

## LIÇÕES DA AUDITORIA (não repetir)

- Arquivos `*_BRASIL.csv` do TSE são consolidados — carregar junto com os por-UF
  DUPLICA tudo (bug pego e corrigido nas doações; validado ao centavo depois).
- CSVs do TSE: latin-1, às vezes com bytes inválidos → converter pra UTF-8 antes do DuckDB.
- CSVs da Câmara têm BOM → decodificar com `utf-8-sig`.
- PMDB→MDB e fusões partidárias NÃO são troca de partido (mapa `_LINHAGEM_PARTIDO`).
- API de despesas da Câmara está morta → CEAP vem dos arquivos `camara.leg.br/cotas/Ano-*.csv.zip`.
- "Leis aprovadas" pela API incluem coautoria em massa → rotular "subscreveu (autor/coautor)".
- Sempre validar um candidato-amostra recontando direto do CSV bruto antes de publicar.
- **(18/08)** DCA I-D: somar `DO4.4*` duplica investimentos (pai + filhos) — usar só o
  total `DO4.4.00.00.00.00`. Bug pego na validação amostral (Aparecida 2016).
- **(18/08)** CSV da API do TCM-GO vem com mojibake MISTO (linhas double-encoded e
  linhas normais) → consertar linha a linha com roundtrip latin-1→utf-8.
- **(18/08)** URL antiga dos dados abertos do CNPJ (dadosabertos.rfb.gov.br) morreu →
  WebDAV público do Nextcloud da RFB (ver `qsa.py`). Empresas0.zip é ~7× maior que os
  demais; downloads longos podem truncar → sempre validar zips (`testzip`) e re-baixar.
- **(18/08)** CNIA: captcha é validado no servidor — não adianta trocar de IP/VPS.
