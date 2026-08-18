# AUDITORIA COMPLETA — 18/08/2026

Quatro frentes independentes (código do pipeline, validação de dados contra as fontes
brutas, front-end/UX/links, jurídico-metodológica), consolidadas aqui. Achados 🔴 foram
**corrigidos nesta mesma data** (seção "Correções aplicadas"); 🟡/🔵 viram backlog.

---

## 1. O QUE FOI VALIDADO E CONFERE (recontagem independente)

- **TCM-GO**: matcher independente sobre as 1.382 linhas × 888 candidatos → mesmos 5
  candidatos, mesmos 9 registros, campo a campo. Nenhum registro faltando ou sobrando.
- **TCE-GO**: os 2 hits conferem com o PDF (CPF completo); varredura dos 888 CPFs → só
  esses 2 mesmo.
- **Siconfi**: recomputado ao **centavo** (Rio Verde e S. J. d'Aliança, 2 anos cada),
  incluindo o deflator IPCA refeito da série do BCB.
- **QSA**: 5 vínculos conferidos no bruto da Receita (linha exata nos Socios*.zip) +
  sanções da GAM LTDA confirmadas no dump oficial do CEIS de hoje; caso negativo (homônimo
  com 1.864 xarás e máscara divergente) corretamente fora.
- **Patrimônio**: 638 candidatos com bens × TSE bruto → **0 divergências**.
- **Contagens**: 888 fichas + index ✓; 40 siconfi = 40 gestão ✓; 451 QSA ✓; 34 sanções PF ✓;
  16.052 PJ ✓; 23.243 vínculos ✓.
- **Links**: 34/35 URLs distintas com HTTP 200.

## 2. CORREÇÕES APLICADAS HOJE (eram 🔴/🟡)

**Pipeline**
1. `download.py`: marcador `.utf8_ok` agora é invalidado na re-extração — sem isso o cron
   diário quebrava do 2º dia em diante (CSV latin-1 lido como UTF-8).
2. `tcu.py`: fallback por nome **restrito a linhas da lista sem CPF** (antes: homônimo de
   listado virava "consta da lista do TCU" mesmo com CPF divergente — risco jurídico
   direto); falha ruidosa se nenhuma coluna reconhecida; arquivo mais recente por mtime.
3. **Higiene de sidecars** (tcmgo, tcego, cnia, qsa, siconfi, gestão): cada rodada limpa a
   pasta antes de gravar — quem sai da lista sai da ficha. `injetar.py` remove da ficha a
   camada cujo sidecar sumiu. (Era o vetor clássico de condenação de agregadores: registro
   mantido após reforma da decisão.)
4. `run_all.py`: **todas as 10 camadas encadeadas** no orquestrador, cada uma isolada em
   subprocesso (fonte fora do ar não derruba o resto; falhas viram sumário no log). Antes o
   cron só atualizava TSE+TCU e as camadas novas congelavam para sempre.
5. `sancoes.py`: fallback de data D-1..D-3 (CGU publica com atraso).
6. `siconfi.py`: cache só grava após JSON válido e não-vazio (antes: HTML de erro ou DCA
   ainda não entregue "envenenava" o cache para sempre).
7. `radar_noticias.py`: whitelist corrigida — `pular.com.br` não passa mais como
   "opopular.com.br" (sufixo permissivo removido).
8. `tcmgo.py`: município normalizado ("Trindade - Fms" → Trindade) no sinal de histórico.
9. `fichas.py`: **filtro LGPD** — CPFs (inclusive de terceiros/co-titulares), contas
   bancárias, agências e placas mascarados nas descrições de bens antes de publicar.
   **90 fichas já publicadas foram limpas (231 descrições); zero CPF formatado restante.**
10. `stubs.py`: descrição SEO agora inclui as camadas novas (TCM/TCE/QSA/Siconfi/IDEB) —
    e as 888 páginas `docs/c/` foram geradas (o botão compartilhar e o sitemap apontavam
    para 404).

**Front-end**
11. `sw.js`: versão do cache agora é datada e o `run_all.py` faz bump automático — sem
    isso, quem já visitou o site **nunca** recebia app.js/style.css novos (cache-first
    congelado). `cron.sh` publica o sw.js.
12. `style.css`: tabelas largas rolam dentro do card no mobile (antes vazavam até 273px —
    a coluna de sanção do QSA ficava fora da tela); pill de situação **visível** no mobile
    (estava `display:none`); nav Metodologia/Privacidade mantido no mobile; contraste do
    cinza `--ink-3` corrigido para WCAG AA (3,1:1 → 4,9:1).
13. `app.js`: datas todas em dd/mm/aaaa (helper único); **"nada consta" com escopo
    declarado + data em TCM/TCE/CGU** (para não-gestor: "a ausência é esperada e não
    significa contas aprovadas"; para ex-gestor: "foi gestor municipal e não aparece na
    lista" — bifurcado pelo histórico da própria ficha); aviso de verificação anti-robô nos
    links de processo do TCM (Turnstile) — mesmo padrão do TCE; sinal "município consta do
    histórico ✓" nos registros TCM; nota "mandato como vice — a gestão é do titular" nos
    blocos IDEB/Siconfi de vices; texto do TCU sem a data órfã "18/12".
14. `index.html`: `og:image` absoluta (era relativa — preview do WhatsApp saía sem
    imagem); rodapé com fontes completas + responsável identificado + contato.

**Jurídico/conteúdo**
15. `privacidade.html`: base legal corrigida (art. 7º, IV e V **não se aplicavam**; agora:
    art. 4º, II, "a" — fins jornalísticos — e, subsidiariamente, art. 7º, IX + §§ 3º-4º +
    art. 23); lista de fontes atualizada (QSA, Siconfi, TCM, TCE, INEP, radar);
    salvaguarda de terceiros nas descrições de bens; **controlador identificado com canal
    e prazos** (48h/7 dias — LGPD art. 18 e Res. CD/ANPD 18/2024).
16. `metodologia.html` **v2.0**: cobre todas as 6 camadas novas; corrige duas afirmações
    que o site desmentia (patrimônio é de 7 eleições, municipais ESTÃO na base); seção
    "níveis de identificação" (CPF completo / nome+6 dígitos / nome+iniciais, com o
    resultado da validação); política de "nada consta"; limitações conhecidas; procedimento
    de correção/contestação com prazos; seção "Quem faz" com responsável nominal e
    declaração de financiamento (art. 57-D da Lei 9.504/97 veda anonimato).
17. `CORRECOES.md`: log público de correções criado (1ª entrada: a limpeza LGPD).

**Verificação pós-correção**: site renderizado em Chromium headless (mobile+desktop):
overflow 0px, 0 erros de console, todos os textos novos presentes, bifurcação
gestor/não-gestor funcionando.

## 3. BACKLOG PRIORIZADO (não bloqueia publicar)

**🟡 Esta semana / antes do lançamento público**
- **Share cards PNG**: `sharecards.py` precisa rodar no deploy (og:image por candidato;
  hoje cai no og-default). Rodar no VPS junto com o cron.
- **Mecanismo de contestação na ficha**: campo `contestacao` por seção + faixa "registro
  contestado pelo candidato em DD/MM" no app.js (o `injetar.py` já permite anexar sem
  rebuild — falta o campo e o render).
- **fichas.py**: deduplicar série patrimonial por (cpf, ano) — CPF com 2 candidaturas no
  mesmo ano (substituição) gera ano repetido e pode pegar o patrimônio do SQ errado.
- **Decisão de produto**: vices continuam com bloco IDEB/Siconfi? (hoje: sim, com a nota
  "a gestão é do titular" — alternativa: remover vices dessas camadas).
- **Portal da Transparência**: link de consulta responde 202 (WAF) a robôs — em navegador
  funciona; monitorar.
- **TTL dos caches** (lista TCM diária, CEAP/votações do ano corrente, `RFB_MES`
  hardcoded): re-baixar por idade, não só por ausência. O `--force` do cron já cobre TCM/TCE.
- **parlamentar.py**: paginação de `deputados_da_uf` (>100 itens some em SP) — pré-escala.
- **doacoes_feitas.py / build_db**: conversão latin-1→utf-8 em streaming (o consolidado
  nacional de GB estoura RAM de VPS modesto) — pré-escala.
- **CNPJ nas listas de contas**: o PDF do TCE tem 22 linhas de PJ (hoje ignoradas por
  design) — cruzar com o QSA dos candidatos (mesma lógica sanções-PJ). Idem irregulares-PJ
  do TCM.

**🔵 Roadmap**
- CNIA via coleta assistida (captcha) — módulo drop-in pronto.
- Linha "Érica Chaves Cruvinel" do PDF TCE com CPF malformado na fonte (10 dígitos) fica
  fora do parse — sem impacto (não é candidata); parser leniente se algum dia importar.
- Documentar critério do recorte `sancoes_pj` (16.052 vs 23.539 do CEIS pleno de hoje).
- Anti-cosmética de escala: só regravar ficha quando o conteúdo (sem `gerado_em`) mudar;
  share cards top-N; QSA via DuckDB read_csv direto nos zips; git história (fichas mudam
  todas todo dia).
- `gestao_numeros.py`: INEP com `verify=False` no fallback TLS → empacotar CA; preferência
  Municipal não deve sobrescrever Pública com dict vazio.
- `resumo_planos.py`: re-resumir quando o PDF do plano mudar (hash).
- Fotos: re-copiar quando o TSE atualizar (hoje `if not exists`).
- UX: mensagem de busca sem resultado; gráfico patrimonial mobile (rótulos pequenos);
  `aria-live` do main; ícone maskable no manifest; dumps/API dos dados agregados; página
  de termos de uso/licença dos dados.

## 4. NOTAS DE FONTE (não são erros nossos — registrar)

- TCM: registro do Catarino tem trânsito (15/10/2018) anterior ao julgamento (14/08/2019)
  no próprio CSV do tribunal.
- TCE: a "Natureza" da lista oficial diverge do "Assunto" do processo no caso Itamar
  (Prestação de Contas × Tomada de Contas Especial) — inconsistência interna do TCE;
  publicamos como está na lista, com link para conferência.
- Siconfi: população de Rio Verde cai 247k→214k entre 2023/2024 na própria API (revisão
  censitária IBGE).

---

# AUDITORIA 2 — 18/08/2026 (noite): camadas novas + site publicado

## Validação de dados (recontagem independente): TUDO CONFERE
Emendas 18/18 ao centavo (e granularidade da base investigada: linhas múltiplas são rateio,
não repetição); votos-chave 4 deputados × 4 votações contra a API oficial ✓ + 15 placares ✓;
ALEGO 44/44 recomputados exatos, matches todos plausíveis; financiamento-2022 3/3 ao centavo,
máscara de CPF em 1.180 sidecars sem exceção; ZERO CPF formatado em todo o docs/data.

## Corrigido nesta rodada (era 🔴/🟡)
1. **Seção "Quem financia" quebrada NO AR** (placeholder `{disponivel:false}` renderizava
   "Quem financia (undefined)" nas 888 fichas) → condição corrigida no app.js.
2. **"não registrou voto" injusto**: suplente sem mandato na data (caso Samuel dos Santos,
   13×) → rótulo "não estava em exercício no período" + nota na tabela de participação.
3. **PEC 45 duplicada no top-15** (turnos com ids de proposição distintos) → dedupe por
   número/ano da matéria extraído da descrição.
4. **Comparador dependia da ordem de seleção** (linha CNIA sumia se o 1º clicado não a
   tivesse) → conjunto de linhas fixo pela união das fichas; TCM/TCE só para GO; dedupe de
   sq repetida na URL; estado zera ao trocar de UF; memoização.
5. **run_all**: emendas rodava ANTES de parlamentar (de quem depende) → reordenado; --force
   propagado a financiamento/emendas; bump do sw.js com hora (não só data).
6. **emendas**: total_pago agora soma Restos a Pagar pagos (antes subestimava bilhões na
   base); guarda de homonímia por Código do Autor; título da seção juridicamente preciso
   ("para onde indicou recursos"); aviso automático quando >50% é "múltiplo"; rótulo
   "Localidade não informada".
7. **alego**: regra automática de subconjunto de nomes REMOVIDA (era mais frouxa que o
   critério declarado) → só exato + aliases verificados manualmente (Anderson Teodoro
   promovido a alias); critério da ficha corrigido para o que o código realmente faz;
   higiene de sidecar no parlamentar.
8. **XSS**: esc() nas interpolações de dados da ALEGO (legislaturas, tipos de lei).
9. **Metodologia v2.1**: cobre votos-chave (critério completo: ≥400, PDL, decisiva, as
   mesmas 15 pra todos), emendas, ALEGO (coleta assistida ~mensal declarada + Nível 4 de
   identificação + cobertura 44/49), quem-financia (corte top-10, PF não cruzado) e
   comparador (conjunto fixo de campos). "Processamento diário" corrigido por camada.
10. **privacidade.html**: doadores/fornecedores PF como titulares (antes de 09/09) + ALEGO
    nas fontes e órgãos de retificação.
11. **UX mobile**: dica "⇢ deslize para ver mais" automática em tabelas que rolam; legenda
    dos rótulos de voto (obstrução/abstenção/Art. 17).

## Backlog (🟡/🔵 remanescentes)
- QSA mobile: célula de sanções alta cria vazio na 1ª linha (quebrar em linha própria).
- Stubs: og:image por candidato (hoje genérica) e descrição citando camadas novas.
- ALEGO: exibir Licenciado/Afastado na tabela de frequência; % alternativo sem penalizar
  falta justificada; PDL fora de "outros atos".
- financiamento: rotular "documento não informado"; filtrar fornecedor "#Nulo"; fonte_url
  por ano (slug CKAN de 2022 mudou — o de 2026 responde 200); não limpar sidecars quando o
  CSV da UF ainda não existe no zip; monitorar 1º snapshot pós-final (parcial×final).
- votos_chave: baixar votacoesVotos ausente na hora (hoje warn+pula); truncamento com "…".
- injetar: restaurar placeholder de financiamento em vez de deletar (hoje inócuo, app.js robusto).
- Changelog de versões da metodologia; anotar robots/termos do SPL no README da coleta.
