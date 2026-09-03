import os
import json
import time
import google.generativeai as genai

def extrair_dados_com_ia(texto_despacho: str, api_key: str) -> dict:
    """
    Usa o modelo Gemini (Google) para extrair UGR, Natureza de Despesa e Favorecido
    do texto do despacho, retornando um dicionário formatado.
    Possui sistema de retry automático contra erros temporários (504 Deadline Exceeded).
    """
    genai.configure(api_key=api_key)
    
    # Usar gemini-flash-lite-latest para máxima velocidade
    model = genai.GenerativeModel('gemini-flash-lite-latest')
    
    prompt = f"""
Você é um especialista em orçamento público e processos do SEI.
Leia o texto do despacho SEI abaixo (que é um pedido de Nota de Crédito) e extraia exatamente as seguintes informações:

1. "ugr": A sigla exata (ex: DGP, DAF, DOR) OU o nome da Unidade Gestora Responsável (UGR) a qual os recursos PERTENCEM, exatamente como aparece no texto. ATENÇÃO: Ignore encaminhamentos ("Encaminhe-se para..."). Busque quem é o dono do recurso (ex: "com recursos da Matriz/DGP", "da DAF", "do DEG"). NÃO INVENTE. Se não estiver CLARAMENTE escrito, retorne "".
2. "nd": A descrição da natureza de despesa (ex: "Capacitação", "Bolsa"). Se não achar, retorne string vazia "".
3. "favorecido": O nome de quem vai receber. Se não achar, retorne "".

4. "descricao_nc": Uma frase curta e direta (máximo 150 caracteres) para ser usada como a 'Descrição da NC' no formulário oficial do SIAFI/SEI. Deve resumir a finalidade do gasto (ex: "Pagamento de bolsa para Domingos", "Inscrição no congresso X para o servidor Y", "Reembolso de certificado digital"). Se não souber, retorne "".

5. "resumo": Um breve resumo (em 1 ou 2 frases) explicando do que se trata o pedido (o que está sendo comprado, pago ou transferido).

Você DEVE retornar APENAS um objeto JSON válido. NÃO INVENTE DADOS que não estão no texto:
{{
    "ugr": "sigla ou nome",
    "nd": "descrição da despesa",
    "favorecido": "nome da pessoa/empresa",
    "descricao_nc": "texto para o campo descrição",
    "resumo": "seu resumo explicativo aqui"
}}

TEXTO DO DESPACHO:
\"\"\"
{texto_despacho[:2500]}
\"\"\"
"""
    
    ultimo_erro = ""
    for tentativa in range(2):
        try:
            # Timeout de 25s permite margem suficiente para a resposta do Gemini
            response = model.generate_content(prompt, request_options={"timeout": 25})
            texto_resposta = response.text.strip()
            if texto_resposta.startswith("```json"):
                texto_resposta = texto_resposta[7:]
            if texto_resposta.startswith("```"):
                texto_resposta = texto_resposta[3:]
            if texto_resposta.endswith("```"):
                texto_resposta = texto_resposta[:-3]
                
            print(f"RESPOSTA BRUTA DA IA (tentativa {tentativa+1}):\n{texto_resposta}", flush=True)
            try:
                dados = json.loads(texto_resposta.strip())
                dados['raw'] = texto_resposta
                return dados
            except Exception as json_err:
                print(f"Erro ao parsear JSON: {json_err}", flush=True)
                return {"raw": texto_resposta, "erro": "A IA não retornou um JSON válido."}
        except Exception as e:
            ultimo_erro = str(e)
            print(f"Tentativa {tentativa+1} falhou com erro na IA: {e}", flush=True)
            if tentativa < 1:
                time.sleep(1) # Aguarda 1s antes de tentar novamente

    return {"erro": f"Servidor do Google ocupado: {ultimo_erro}"}

