# DPO — Sistema de Notas de Crédito

Sistema web para emissão automatizada de Notas de Crédito Orçamentárias no SIAFIWeb — UnB/DPO.

## Funcionalidades

- Upload de Despacho SEI (PDF, HTML ou ZIP do processo completo)
- Extração automática dos dados do despacho
- Cruzamento com planilha orçamentária da DOR/DPO
- Sugestão automática de Células de Origem e Destino
- Geração do XML no formato SIAFIWeb
- Validação de campos obrigatórios antes da geração

## Tecnologias

- Python 3.11 + Flask 3.0
- pdfplumber (extração de PDF)
- openpyxl (leitura de planilha Excel)
- Gunicorn (servidor WSGI)
- Deploy: Render.com

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

URL: https://dpo-nota-credito.onrender.com

## Estrutura

```
sistema_nc/
├── app.py                 # Servidor Flask
├── parser_sei.py          # Extração de dados do despacho SEI
├── parser_planilha.py     # Leitura e cruzamento com planilha orçamentária
├── gerador_xml.py         # Geração do XML SIAFIWeb
├── templates/
│   └── index.html         # Interface web
├── data/
│   └── planilha_base.xlsx # Planilha orçamentária base
├── requirements.txt
└── Procfile
```

## Uso Local

```bash
pip install -r requirements.txt
python app.py
# Acesse: http://localhost:5000
```
