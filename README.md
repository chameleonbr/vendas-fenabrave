# Emplacamentos Fenabrave — Streamlit

Aplicativo para consultar e agrupar os emplacamentos mensais publicados pela Fenabrave entre janeiro de 2021 e agosto de 2026.

## Executar

```bash
uv sync
uv run streamlit run app.py
```

Testes: `uv run pytest`.

Com Docker: `docker compose up --build` (a porta 8501 só fica exposta na rede interna do Compose;
para acessar localmente, adicione `ports: ["8501:8501"]`).

## Deploy no Dokploy

O `docker-compose.yml` usa `expose: 8501` em vez de `ports`, então o Traefik do Dokploy faz o
roteamento sem publicar porta no host.

1. **Create Service → Compose**, provider GitHub (ou Git) apontando para
   `https://github.com/chameleonbr/vendas-fenabrave`, branch `main`, compose path `./docker-compose.yml`.
2. **Deploy**.
3. Em **Domains**, adicione o domínio com **Service Name** `app` e **Container Port** `8501`
   (ative HTTPS/Let's Encrypt se quiser). Redeploy para aplicar.

Para atualizar, basta dar push na `main` e redeploy (ou ativar Auto Deploy).

## Recursos

- Agrupamento por ano, trimestre ou mês.
- Detalhamento por marca, modelo, **tipo** (hatch, sedã, SUV, minivan, picape, furgão, chassi leve,
  off-road) e **categoria** com porte (SUV compacto, picape média, furgão grande...).
- Filtros de período, segmento, carroceria, marca e modelo.
- Chave **Números / Percentual**: em percentual tudo vira participação no total do período,
  o que remove a sazonalidade (janeiro fraco, novembro/dezembro forte) e mostra quem de fato
  ganha ou perde mercado.
- Indicadores com variação contra o mesmo período do ano anterior, tabela detalhada e CSV.
- Comparações anuais mês a mês: um ano incompleto (jan–ago) é medido contra os mesmos meses do ano
  anterior, nunca contra o ano cheio — o app avisa quando o último período está parcial.

### Abas de análise

| Aba | O que responde |
| --- | --- |
| Evolução | Tendência por série, com acumulado ou média móvel de 12 meses. |
| Mapa do mercado | Treemap (Plotly) com hierarquia configurável — tipo, categoria, marca, modelo. Tamanho do bloco = volume, cor = variação anual. Clique entra no nível. |
| Ranking | Maiores do recorte, placar com minigráfico por série (total, participação, Δ anual, Δ participação) e evolução de posição no ranking. |
| Participação | Ganho e perda de share ao longo do tempo. |
| Momentum | Mercado ano contra ano, quem puxou o crescimento do último período em volume absoluto e o mapa tamanho × crescimento. |
| Mix de carroceria | Como a demanda migra entre carrocerias, com placar por categoria. |
| Sazonalidade | Mapa ano × mês, em volume ou em % do próprio ano. |

## Classificação de carroceria

`data/carrocerias.csv` liga cada par segmento + marca + modelo do ranking Fenabrave a um `tipo` e a
uma `categoria` (tipo + porte). Cobre os 266 pares existentes na base. Para ajustar uma
classificação, edite a linha correspondente — o app lê o arquivo direto, sem outra etapa.

## Limitação da fonte

A Fenabrave publica até 50 modelos de automóveis e até 50 comerciais leves por mês. Portanto, somas baseadas em modelos não incluem veículos fora do ranking. A visão por marca usa o ranking mensal das 21 marcas publicado pela Fenabrave.
