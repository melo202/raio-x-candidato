# Mapa de fontes públicas — Raio-X do Candidato

**Estudo de aprofundamento · 18/08/2026 · uso interno**

Este documento mapeia todas as fontes públicas relevantes para a ficha do candidato,
com o estado de implementação, o método de cruzamento e — o mais importante — o
**tratamento jurídico** de cada uma. A regra transversal do projeto: nunca publicar
inferência, acusação ou rótulo ("fraude", "escândalo", "corrupto"); publicar somente
o registro oficial, com processo, órgão, datas, contexto obrigatório e link da fonte.
Quem qualifica é o eleitor, com o dado na mão.

---

## 1. Implementadas e rodando

| Fonte | O que entrega | Chave | Risco jurídico e mitigação |
|---|---|---|---|
| TSE — consulta_cand (2014-2026, gerais + municipais) | Ficha básica, situação do registro, histórico eleitoral, mandatos | CPF | Baixo. Dado publicado por força de lei (Lei 9.504/97). CPF sempre mascarado na exibição. |
| TSE — bem_candidato (7 eleições) | Evolução patrimonial declarada | CPF | Médio. Mitigação: valores como declarados, disclaimer fixo (herança, venda de empresa etc.), sem correção monetária anunciada, zero adjetivo. |
| TSE — rede_social_candidato | Redes e site oficiais | SQ | Baixo. Declarado pelo próprio candidato. |
| TSE — receitas de campanha 2022/2024 | Doações que o candidato FEZ (cruzamento invertido pelo CPF do doador) | CPF doador | Baixo-médio. Doar é lícito e regulamentado; nota fixa dizendo isso. Validado contra CSV bruto ao centavo. |
| INEP — IDEB municípios (série 2005-2023) | "Gestão em números" de ex-prefeitos: IDEB da rede municipal no mandato vs média estadual | município+UF normalizado | Médio (risco de atribuição indevida). Mitigação: série lado a lado com média estadual, disclaimer fixo "indicador é contexto, não veredito". |
| CGU — CEIS / CNEP / CEAF | Sanções administrativas (inidoneidade, Lei Anticorrupção, expulsão da adm. federal) | CEIS/CNEP-PF: CPF completo. CEAF: CPF mascarado + nome (dupla coincidência obrigatória) | Alto se mal feito; controlado aqui. Mitigação: só registro oficial + processo + órgão + prazo + disclaimer "sanção ≠ condenação criminal, pode estar sub judice" + link da consulta oficial da CGU. PJs ficam em tabela própria aguardando o QSA. |
| Câmara — Dados Abertos (API + CSVs de votos) | Projetos apresentados, normas sancionadas na carreira, participação em votações nominais ano a ano, cota (CEAP) | **CPF exato** (o detalhe do deputado na API traz CPF) | Baixo. Mitigação: nota fixa (ausência pode ter justificativa legal; quantidade ≠ qualidade; CEAP é despesa regulamentada). |
| Google News RSS c/ whitelist | Radar de imprensa (majoritários) | nome de urna + estado | Médio. Mitigação: whitelist fechada de veículos profissionais, só título+veículo+link, zero resumo, aviso de homonímia. |
| TCU — contas julgadas irregulares | Camada 6 | CPF/nome | Arquivo manual (WAF); cruzador pronto e testado. Disclaimer LC 64/90 fixo. |
| TSE — DivulgaCandContas API | Processos da candidatura (impugnação, AIJE) | SQ | Módulo pronto; rodar do VPS (bloqueia datacenter). É dado do próprio TSE — risco baixo. |
| TCM-GO — contas com parecer pela rejeição / julgadas irregulares (`tcmgo.py`, 18/08) | 1.382 registros oficiais via API REST `ws.tcm.go.gov.br/api/rest/dados/contas-irregulares` (CSV, mojibake misto tratado); em GO: 5 candidatos, 9 registros, com link direto ao processo eletrônico | CPF mascarado (só 2 dígitos iniciais) + nome → **dupla coincidência obrigatória**; sinal extra exibido: município do registro consta do histórico do candidato | Mesmo enquadramento do TCU: contas de prefeito quem julga em definitivo é a Câmara Municipal; disclaimer LC 64/90 fixo; validado no bruto (1 homônimo rejeitado). |
| Siconfi/Tesouro — DCA Anexos I-C e I-D (`siconfi.py`, 18/08) | Finanças do município no mandato dos 40 ex-gestores: receita realizada (líquida de deduções FUNDEB), despesa empenhada, investimentos — por habitante e corrigidos pelo IPCA (SGS 433/BCB) a preços do último ano | município → cod. IBGE; série mandato + ano-base | Médio (atribuição indevida). Mitigação idêntica ao IDEB: série com ano-base, disclaimer fixo "orçamento depende de transferências e da Câmara". Cuidado técnico: usar SÓ o total 4.4 de investimentos (subcontas duplicam a soma — bug pego na validação). |
| Receita Federal — QSA dados abertos do CNPJ (`qsa.py`, 18/08) | Participações societárias: 23.243 vínculos de 9.852 candidatos no Brasil (451 em GO), razão social resolvida p/ 100% dos 22.877 CNPJs; cruzado com `sancoes_pj` (16.052 PJs): 31 vínculos com empresa sancionada no país, 1 candidato em GO | CPF mascarado ***NNNNNN** (6 dígitos centrais, igual CEAF) + nome → **dupla coincidência obrigatória** | Ser sócio é lícito (disclaimer fixo); sanção é DA EMPRESA, nunca atribuída ao sócio; os dois fatos lado a lado, sem frase-ponte causal. Fonte nova: a URL antiga (dadosabertos.rfb.gov.br) morreu — acesso atual por WebDAV público do Nextcloud da RFB (share `YggdBLfdninEJX9`, pastas mensais `2026-08/Socios*.zip` + `Empresas*.zip`, ~2GB). |

## 2. Próximas — alto valor, viáveis, ordem sugerida

**2.1 CNJ — Cadastro Nacional de Condenações por Improbidade e Inelegibilidade (CNIA/CNCIAI).**
A resposta juridicamente correta para "teve escândalo?": condenações CÍVEIS por
improbidade com trânsito ou órgão colegiado, publicadas pelo próprio CNJ. Consulta
pública em `www.cnj.jus.br/improbidade_adm/consultar_requerido.php`. Não tem dump aberto.
**Descoberta de 18/08/2026: a consulta valida reCAPTCHA no SERVIDOR** (o POST sem token
volta "Por favor, resolva o recaptcha") — ou seja, o bloqueio NÃO é de IP: **rodar do
VPS não resolve**. Caminhos que funcionam: (a) coleta assistida pelo navegador real
(Claude in Chrome na máquina do Bruno, lote dirigido: ~60 nomes de majoritários +
ex-gestores já cobrem o essencial); (b) consulta manual dirigida. O módulo `cnia.py`
está pronto no padrão drop-in do TCU: qualquer CSV solto em `data/cnia/` é cruzado
(CPF completo = certeza; nome exato = marcado p/ aviso de homonímia). Exibição: número
do processo, tribunal, trânsito, registro — e nada além. Segue sendo O item mais
valioso do bloco "integridade".

**2.2 TCM-GO — pareceres ano a ano (aprovação E rejeição).**
A lista de rejeições/irregulares já está implementada (seção 1). O passo seguinte é o
espelho completo por ex-gestor — parecer de CADA exercício, incluindo aprovações
("mesma ficha para todos" pede simetria). O caminho é o widget `portalwidgets/
consulta-processo` do TCM (JSF/PrimeFaces, scraping stateful, esforço médio) ou
pedido LAI de dump. Fase 2.

**2.3 TCE-GO — contas julgadas irregulares (âmbito ESTADUAL).**
Complemento do TCM-GO descoberto em 18/08: Goiás tem DOIS tribunais de contas —
o TCM-GO julga contas municipais (prefeitos etc., já implementado) e o TCE-GO as
estaduais (governador, secretários de estado, dirigentes de autarquias estaduais).
O TCE-GO publica a "Relação de responsáveis com contas julgadas irregulares" em
`portal.tce.go.gov.br/contas-irregulares`, mas o dado vive num painel Qlik Sense
(`paineis.tce.go.gov.br`, app 67f0715a-...) — a Engine API exige sessão e o
websocket é bloqueado fora do navegador (403/reset testados). Caminho prático:
abrir o painel no Chrome e usar o botão de exportação do Qlik (XLSX) → soltar o
arquivo em `data/tcego/` → módulo drop-in no molde do tcmgo.py (o motor de
cruzamento por nome+CPF já existe). Relevante para candidatos que foram gestores
ESTADUAIS — inclusive os majoritários.

**2.4 Emendas parlamentares (Portal da Transparência / Câmara).**
Emendas por autor com destino por município → cruzar com o município-base eleitoral
(derivável da votação por município, dataset TSE `votacao_candidato_munzona`). Fato
público; contexto fixo: emenda é prerrogativa constitucional.

**2.5 Senado — API de matérias e votações** (para os senadores candidatos): mesma
lógica da Câmara, XML/JSON aberto.

**2.6 Assembleia Legislativa de Goiás** (deputados estaduais, 587 candidatos):
não há API padronizada; scraping do portal da ALEGO (presenças e proposições) —
esforço médio, valor alto localmente. Fase 2.

## 3. Sobre "fraudes em licitação" — a fronteira

O que NÃO fazer: qualquer texto que conecte o candidato a "fraude" sem condenação —
mesmo com reportagem publicada. Risco: direito de resposta (Lei 13.188/15),
representação eleitoral, dano moral, remoção judicial às vésperas da eleição.

O que fazer (cada item é um fato oficial isolado, linkado, sem síntese acusatória):
1. Condenação por improbidade no CNIA (2.1) → publicar.
2. Contas rejeitadas pelo TCM/TCE/TCU (2.2 e camada 6) → publicar.
3. Sanção em CEIS/CNEP/CEAF (implementado) → publicar.
4. Sócio de empresa sancionada (IMPLEMENTADO 18/08 via QSA) / contratada pelo ente que geriu → publicar os
   dois fatos separados, lado a lado, sem frase-ponte causal.
5. Ação penal/improbidade EM CURSO (DataJud/CNJ): publicável com cautela máxima —
   classe, número e link, rotulado "em tramitação, sem condenação; presunção de
   inocência", nunca em destaque, nunca agregado em "número de processos" (que vira
   score às avessas). Excluir segredo de justiça. Recomendação: só na fase 2, depois
   de revisão jurídica dedicada (o advogado do projeto é você).
6. Reportagens: permanecem no Radar (whitelist, título+link), nunca no corpo da ficha.

## 4. Descartadas / adiadas (e por quê)

- "Lista suja" do trabalho escravo (MTE): pública e oficial, mas raríssimo atingir
  candidato PF diretamente; entra via QSA no futuro.
- Sanções estaduais/municipais fora do CEIS: fragmentadas em ~5.600 fontes; o CEIS
  já consolida boa parte por convênio.
- Redes sociais/conteúdo de terceiros como fonte de "escândalo": nunca — é
  exatamente o vetor de fake news que o projeto existe para combater.
- Score/índice de integridade: nunca, por princípio (e é a nossa defesa jurídica).

## 5. Regras de exibição do bloco "Integridade" (resumo pro front)

1. Seção chama "Registros em cadastros oficiais" — nunca "ficha suja", "escândalos".
2. Ausência de registro exibe "✓ nada consta" **com a data da consulta** (nada consta
   é informação valiosa e é o caso da maioria).
3. Todo registro: cadastro, processo, órgão, datas, situação + link da consulta oficial.
4. Disclaimers fixos por cadastro (já no pipeline) — não editáveis por ficha.
5. Direito de correção: canal público; divergência confirmada corrige na rodada
   seguinte com changelog público no repositório.


## ADENDO 18/08/2026 (auditoria 2)

Camadas que saíram do planejamento e JÁ RODAM: emendas parlamentares (base CGU, matching por
nome parlamentar + código de autor), votos nominais nas 15 matérias de maior quórum (CSVs da
Câmara, critério objetivo declarado), ALEGO/SPL (coleta assistida por navegador — datacenter
bloqueado; dump mensal em data/raw/alego/), quem-financia (pronto, ativa em 09/09). Detalhes
de critérios: docs/metodologia.html v2.1.

## PARECER 18/08 — camada "irregularidades em licitações na gestão" (estudo de viabilidade)

Pergunta do produto: "houve registro oficial de irregularidade em licitação do ente durante o
mandato do candidato?" Fontes investigadas e veredito:

1. **CGU e-aud (relatorios.cgu.gov.br / eaud.cgu.gov.br)** — a fonte IDEAL: relatórios de
   auditoria com filtros de Localidade e grupo "Fiscalização de Entes Federativos". PORÉM a
   API (`/api/auth/relatorio`) responde 401 até para o navegador sem o token da SPA, e a UI
   não reage a automação simples. Caminho realista: sessão assistida no Chrome mapeando o
   fluxo de token (1 sessão de investigação) → depois coleta como a da ALEGO. VIÁVEL, custo
   médio. É a melhor candidata a próxima camada.
2. **dados.gov.br (CKAN)** — a API agora exige chave gratuita (login gov.br). AÇÃO BRUNO:
   gerar a chave em dados.gov.br/perfil → com ela, verificar se o dataset da CGU tem CSV
   direto (se tiver, o custo cai pra baixo).
3. **TCM-GO processos por município** — consulta com captcha Turnstile; só assistido.
4. **CEIS por órgão sancionador × mandato** — dado que JÁ TEMOS no banco (sancoes_pj tem
   órgão + datas). Mas semanticamente mostra "a gestão sancionou empresas" (enforcement da
   própria prefeitura), NÃO "a gestão fraudou" — não serve como camada de irregularidade;
   pode virar métrica neutra futura.
5. **Importante (jurídico)**: a palavra "fraude" nunca entra — só "relatório oficial de
   fiscalização/auditoria do órgão X sobre o ente Y no período Z", com link. As Tomadas de
   Contas Especiais do TCM/TCE já publicadas nas fichas cobrem parte da pergunta hoje.
