# nutricheck/api_flask.py
import os
import json
import base64
import io

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from PIL import Image

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurar a API Key do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
gemini_sdk_configured = False
client = None

if not GEMINI_API_KEY or not GEMINI_API_KEY.startswith("AIza"):
    print("Erro Crítico: Chave da API do Gemini não encontrada ou inválida no arquivo .env.")
else:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("Cliente Gemini SDK inicializado com sucesso.")
        gemini_sdk_configured = True
    except AttributeError as e:
        print(f"Erro ao inicializar o cliente Gemini SDK: genai.Client não encontrado. Verifique a instalação da biblioteca 'google-genai'. Detalhes: {e}")
        gemini_sdk_configured = False
    except Exception as e:
        print(f"Erro inesperado ao inicializar o cliente Gemini SDK: {e}")
        gemini_sdk_configured = False

VALID_API_TOKEN = "f63e69f223d54a858d136b9f72e0c0a4"

ANALISE_INDIVIDUAL_SYSTEM_PROMPT = """Você é um especialista em nutrição e segurança alimentar, com a capacidade de analisar imagens de rótulos de produtos alimentícios e buscar informações complementares na internet. O usuário irá fornecer UMA ou MAIS imagens de um rótulo de produto alimentício. Sua tarefa é fornecer uma análise detalhada do produto, seguindo as seguintes etapas e retornando os resultados EXCLUSIVAMENTE no formato JSON especificado.

**Contexto:**

O usuário forneceu [número de imagens] imagens do rótulo de um produto alimentício. Sua missão é analisar TODAS as imagens fornecidas, extrair informações relevantes de CADA UMA e COMBINÁ-LAS para fornecer a análise mais completa e precisa possível do produto como um todo.

**Instruções:**

1.  **Análise das Imagens:** Examine CADA uma das [número de imagens] imagens fornecidas. As imagens podem mostrar diferentes partes do mesmo produto (frente, verso, tabela nutricional, lista de ingredientes). É crucial que você consolide as informações de todas as imagens.
    * **Nome do Produto e Marca:** Identifique o nome completo do produto e sua marca. Verifique TODAS as imagens para encontrar a representação mais clara e completa do nome e da marca. Se diferentes imagens mostrarem partes do nome, combine-as.
    * **Tipo de Produto:** Determine o tipo de produto (ex: azeite, biscoito, cereal, bebida).
    * **Lista de Ingredientes:** Encontre a lista de ingredientes. Ela geralmente está em uma das faces do rótulo. Transcreva a lista COMPLETA.
    * **Informações Nutricionais:** Localize a tabela nutricional. Extraia TODOS os dados presentes.
    * **Outras Informações Relevantes:** Busque por selos de certificação, alegações (ex: "sem glúten", "orgânico"), peso líquido, etc., em QUALQUER uma das imagens.
    * **Consolidação:** Se uma informação (ex: nome do produto) aparecer em múltiplas imagens, use a versão mais completa ou combine as informações. Se houver informações nutricionais parciais em uma imagem e complementares em outra, combine-as para obter a tabela completa.

2.  **Priorização das Informações:** Se houver informações conflitantes entre as imagens (o que deve ser raro para o mesmo produto), priorize as informações encontradas na lista de ingredientes e na tabela nutricional oficial. Em caso de dúvida sobre qual informação é a mais correta para um campo específico (ex: nome do produto), tente inferir a partir do contexto global das imagens.

3.  **Busca de Informações Online:** Utilize as informações consolidadas e identificadas nas imagens (especialmente nome, marca, e tipo de produto) para buscar na internet dados técnicos e nutricionais detalhados sobre o produto. Priorize fontes confiáveis como sites oficiais de fabricantes, sites de nutrição reconhecidos, órgãos reguladores e artigos científicos. Esta busca pode ajudar a complementar ou validar dados extraídos dos rótulos.

4.  **Extração de Dados (Resultado Final Combinado):** Com base em TODAS AS IMAGENS e na PESQUISA ONLINE, extraia as seguintes informações:
    * Lista COMPLETA de Ingredientes: (Liste todos os ingredientes presentes no rótulo e/ou encontrados na internet, separados por vírgulas. Seja completo e preciso.)
    * Informações Nutricionais COMPLETAS: (Extraia todos os dados da tabela nutricional, incluindo: Valor Energético, Carboidratos, Proteínas, Gorduras Totais, Gorduras Saturadas, Gorduras Trans, Fibra Alimentar, Sódio, e quaisquer outras vitaminas ou minerais listados. Se não encontrar algum valor, deixe em branco.)

 5.  **Avaliação Nutricional:** Utilizando TODAS as informações consolidadas das imagens e da pesquisa online (especialmente a lista completa de ingredientes e os valores nutricionais), avalie a qualidade nutricional do produto em uma escala de 0 a 100, considerando os seguintes critérios (os pesos são importantes):
     * Presença de ingredientes naturais e integrais: (Peso: 30%)
     * Ausência de ingredientes artificiais (corantes, conservantes, aromatizantes, adoçantes artificiais): (Peso: 30%)
     * Baixo teor de açúcar adicionado: (Peso: 15%)
     * Baixo teor de sódio: (Peso: 15%)
     * Baixo teor de gorduras saturadas e ausência de gorduras trans: (Peso: 10%)

6.  **Classificação por Cores:** Classifique o produto com uma cor com base na pontuação:
    * Verde: 80-100 (Produto Excelente)
    * Amarelo: 60-79 (Produto Bom, Consumo Moderado)
    * Laranja: 40-59 (Produto Regular, Atenção ao Consumo)
    * Vermelho: 0-39 (Produto Ruim, Evitar)

7.  **Identificação de Ingredientes Controversos:** Identifique e liste ingredientes que são frequentemente considerados controversos devido a potenciais efeitos negativos na saúde (ex: corantes artificiais, glutamato monossódico, xarope de frutose, gordura vegetal hidrogenada).

8.  **Alerta Principal:** Crie uma frase curta e impactante que resume a avaliação do produto (ex: "Excelente fonte de fibras!", "Alto teor de sódio, use com moderação", "Evite devido aos ingredientes artificiais").

**Formato de Saída (JSON):**

Retorne os resultados EXCLUSIVAMENTE no seguinte formato JSON. É CRUCIAL que a resposta seja um JSON válido e bem formatado:

```json
{
  "servico": "analise_individual",
  "nome_produto": "[Nome Completo do Produto]",
  "pontuacao": "[Número de 0 a 100]",
  "cor": "[Verde/Amarelo/Laranja/Vermelho]",
  "alerta_principal": "[Frase Curta e Impactante]",
  "ingredientes": ["[Ingrediente 1]", "[Ingrediente 2]", "[Ingrediente 3]", "..."],
  "informacoes_nutricionais": {
    "valor_energetico": "[Valor em kcal/kJ]",
    "carboidratos": "[Valor em gramas]",
    "proteinas": "[Valor em gramas]",
    "gorduras_totais": "[Valor em gramas]",
    "gorduras_saturadas": "[Valor em gramas]",
    "gorduras_trans": "[Valor em gramas]",
    "fibra_alimentar": "[Valor em gramas]",
    "sodio": "[Valor em miligramas]",
    "[Outras Vitaminas/Minerais]": "[Valor]"
  },
  "ingredientes_controversos": ["[Ingrediente 1]", "[Ingrediente 2]", "..."],
  "justificativa_pontuacao": "[Parágrafo curto explicando a pontuação e os principais fatores que influenciaram a avaliação]"
}
```"""

def validate_request_token(request_token_to_check):
    return request_token_to_check == VALID_API_TOKEN

def process_base64_image(base64_string_com_prefixo):
    try:
        header, encoded = base64_string_com_prefixo.split(',', 1)
        base64_data_pura = encoded
        image_bytes = base64.b64decode(base64_data_pura)
        img_pil = Image.open(io.BytesIO(image_bytes))
        if img_pil.mode not in ("RGB"):
             img_pil = img_pil.convert("RGB")
        return img_pil
    except Exception as e:
        print(f"Erro ao processar imagem base64: {e}")
        return None

@app.route('/analisar', methods=['POST'])
def analisar_rotulo_endpoint():
    global client
    if not gemini_sdk_configured or not client:
        return jsonify({"status": "erro_configuracao_api", "mensagem": "Cliente API Gemini não configurado ou inicializado corretamente no servidor."}), 503

    try:
        auth_header = request.headers.get('Authorization')
        token_recebido_do_header = None
        if auth_header and auth_header.startswith('Bearer '):
            token_recebido_do_header = auth_header.split(' ')[1]
        
        if not validate_request_token(token_recebido_do_header):
            return jsonify({"status": "erro_autenticacao", "mensagem": "Token da API (interna) inválido ou ausente no cabeçalho Authorization."}), 401

        data = request.get_json()
        if not data:
            return jsonify({"status": "erro_requisicao", "mensagem": "Nenhum dado JSON recebido."}), 400

        # --- INÍCIO DO DEBUG: Mostrar JSON recebido do PHP ---
        print("\n--- JSON Recebido do PHP na API Python (`/analisar`) ---")
        try:
            # Tenta imprimir formatado (pretty print)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            if 'imagens' in data and isinstance(data['imagens'], list):
                print(f"Número de strings de imagem (base64) recebidas no payload: {len(data['imagens'])}")
                # Opcional: imprimir os primeiros N caracteres de cada string base64 para verificar o formato
                # for i, img_b64_str in enumerate(data['imagens']):
                #     print(f"  Imagem {i+1} (primeiros 70 chars): {img_b64_str[:70]}...")
            else:
                print("Campo 'imagens' não encontrado ou não é uma lista no payload.")
        except Exception as e:
            print(f"Erro ao tentar imprimir o JSON recebido (ou verificar imagens): {e}")
            print("Dados brutos recebidos (como string, se possível):")
            print(request.data.decode('utf-8', errors='ignore')) # Tenta decodificar como string
        print("---------------------------------------------------\n")
        # --- FIM DO DEBUG ---

        servico_solicitado = data.get('servico')
        imagens_base64_recebidas = data.get('imagens')

        if not all([servico_solicitado, imagens_base64_recebidas]):
            return jsonify({"status": "erro_requisicao", "mensagem": "Dados faltando no corpo JSON: 'servico' ou 'imagens' não fornecidos."}), 400
        
        if not isinstance(imagens_base64_recebidas, list) or not imagens_base64_recebidas:
            return jsonify({"status": "erro_requisicao", "mensagem": "'imagens' deve ser uma lista não vazia de strings base64."}), 400

        system_prompt_para_gemini_base = ""
        if servico_solicitado == "analise_individual":
            system_prompt_para_gemini_base = ANALISE_INDIVIDUAL_SYSTEM_PROMPT
        else:
            return jsonify({"status": "erro_servico", "mensagem": f"Serviço '{servico_solicitado}' desconhecido ou não configurado com prompt específico."}), 400

        imagens_pil_processadas = []
        for i, img_b64 in enumerate(imagens_base64_recebidas):
            print(f"Processando imagem recebida {i+1}/{len(imagens_base64_recebidas)}...")
            img_pil = process_base64_image(img_b64)
            if img_pil is None:
                print(f"Falha ao processar imagem {i+1}. String base64 (primeiros 70 chars): {img_b64[:70]}...")
                return jsonify({"status": "erro_imagem", "mensagem": f"Falha ao processar uma das imagens base64 fornecidas (imagem {i+1})."}), 400
            imagens_pil_processadas.append(img_pil)
        
        print(f"Total de imagens PIL processadas com sucesso: {len(imagens_pil_processadas)}")

        if not imagens_pil_processadas: # Checagem extra caso o loop não adicione nada mas não retorne erro antes
            return jsonify({"status": "erro_imagem", "mensagem": "Nenhuma imagem foi processada com sucesso."}), 400
            
        system_prompt_final = system_prompt_para_gemini_base.replace("[número de imagens]", str(len(imagens_pil_processadas)))
        
        partes_do_conteudo = [system_prompt_final]
        for img_pil in imagens_pil_processadas:
            partes_do_conteudo.append(img_pil)

        print(f"Enviando para Gemini (generate_content) com modelo 'gemini-2.0-flash'. System prompt incluído (primeiras 100 chars): {system_prompt_final[:100]}...")
        print(f"Número de imagens PIL na lista 'partes_do_conteudo' (excluindo o prompt): {len(imagens_pil_processadas)}")
        print(f"Número total de partes no 'contents' (1 prompt + imagens): {len(partes_do_conteudo)}")

        response_gemini = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=partes_do_conteudo
        )

        resposta_texto_gemini = response_gemini.text
        if resposta_texto_gemini.startswith("```json"):
            resposta_texto_gemini = resposta_texto_gemini[len("```json"):]
        if resposta_texto_gemini.endswith("```"):
            resposta_texto_gemini = resposta_texto_gemini[:-len("```")]
        resposta_texto_gemini = resposta_texto_gemini.strip()

        print(f"Resposta bruta do Gemini (após limpeza básica, primeiras 500 chars):\n{resposta_texto_gemini[:500]}...")

        try:
            resultado_analise_json = json.loads(resposta_texto_gemini)
            resultado_analise_json["servico"] = servico_solicitado 
            return jsonify(resultado_analise_json), 200
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON da resposta do Gemini: {e}")
            print(f"Texto completo recebido do Gemini que causou o erro:\n{response_gemini.text}")
            return jsonify({
                "status": "erro_gemini_response",
                "mensagem": "A API Gemini retornou uma resposta que não é um JSON válido.",
                "detalhes_resposta_gemini": response_gemini.text
            }), 500

    except Exception as e:
        print(f"Erro inesperado na API: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "erro_interno_servidor", "mensagem": f"Erro interno: {str(e)}"}), 500

# ... (restante do código get_image_base64_string, run_manual_gemini_test, if __name__ == '__main__':)
# Nenhuma alteração necessária nessas partes para este debug específico.
# A função run_manual_gemini_test já foi atualizada para testar com múltiplas imagens.

def get_image_base64_string(image_path):
    try:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        base64_encoded_data = base64.b64encode(image_bytes)
        base64_string = base64_encoded_data.decode('utf-8')
        image_type = "jpeg"
        if image_path.lower().endswith(".png"):
            image_type = "png"
        return f"data:image/{image_type};base64,{base64_string}"
    except FileNotFoundError:
        print(f"Erro: Arquivo de imagem não encontrado em '{image_path}'")
        return None
    except Exception as e:
        print(f"Erro ao converter imagem para base64: {e}")
        return None

def run_manual_gemini_test():
    global client
    if not gemini_sdk_configured or not client:
        print("Teste manual não pode ser executado: Cliente API Gemini não configurado ou inicializado.")
        return

    print("\n--- Iniciando Teste Manual Direto com Gemini ---")
    
    nome_arquivo_imagem_teste1 = "mineirinho.jpg" 
    nome_arquivo_imagem_teste2 = "rotulo_mineirinho.jpg" 

    imagem_base64_teste1 = get_image_base64_string(nome_arquivo_imagem_teste1)
    imagem_base64_teste2 = get_image_base64_string(nome_arquivo_imagem_teste2)

    imagens_pil_teste = []
    if imagem_base64_teste1:
        img_pil1 = process_base64_image(imagem_base64_teste1)
        if img_pil1:
            imagens_pil_teste.append(img_pil1)
            print(f"Imagem de teste 1 ('{nome_arquivo_imagem_teste1}') carregada.")
        else:
            print(f"Falha ao processar imagem de teste 1 ('{nome_arquivo_imagem_teste1}').")

    if imagem_base64_teste2: 
        img_pil2 = process_base64_image(imagem_base64_teste2)
        if img_pil2:
            imagens_pil_teste.append(img_pil2)
            print(f"Imagem de teste 2 ('{nome_arquivo_imagem_teste2}') carregada.")
        else:
            print(f"Falha ao processar imagem de teste 2 ('{nome_arquivo_imagem_teste2}').")

    if not imagens_pil_teste:
        print(f"Nenhuma imagem de teste foi carregada. Verifique os arquivos. Teste abortado.")
        return

    print(f"Número de imagens para o teste manual: {len(imagens_pil_teste)}")

    system_prompt_teste = ANALISE_INDIVIDUAL_SYSTEM_PROMPT.replace("[número de imagens]", str(len(imagens_pil_teste)))
    
    partes_do_conteudo_teste = [system_prompt_teste]
    for img_pil in imagens_pil_teste:
        partes_do_conteudo_teste.append(img_pil)
    
    try:
        print(f"Enviando para Gemini (generate_content - TESTE MANUAL com 'gemini-2.0-flash'). System prompt incluído (primeiras 100 chars): {system_prompt_teste[:100]}...")
        
        response_gemini = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=partes_do_conteudo_teste
        )

        resposta_texto_gemini = response_gemini.text
        if resposta_texto_gemini.startswith("```json"):
            resposta_texto_gemini = resposta_texto_gemini[len("```json"):]
        if resposta_texto_gemini.endswith("```"):
            resposta_texto_gemini = resposta_texto_gemini[:-len("```")]
        resposta_texto_gemini = resposta_texto_gemini.strip()
        
        print("\n--- Resposta do Gemini (Teste Manual) ---")
        print(resposta_texto_gemini)
        print("--- Fim da Resposta do Gemini (Teste Manual) ---\n")

        try:
            resultado_json_teste = json.loads(resposta_texto_gemini)
            print("JSON da resposta do Gemini parseado com sucesso (teste manual):")
            print(json.dumps(resultado_json_teste, indent=4, ensure_ascii=False))
        except json.JSONDecodeError:
            print("A resposta do Gemini (teste manual) não foi um JSON válido, mas foi impressa acima.")
            print(f"Resposta completa que falhou no parse JSON: {response_gemini.text}")

    except Exception as e:
        print(f"Erro durante o teste manual com Gemini: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    if not gemini_sdk_configured or not client:
        print("Cliente Gemini não inicializado. Verifique a chave da API e a configuração.")
    else:
        # run_manual_gemini_test() 
        
        print("\nIniciando servidor Flask em http://0.0.0.0:5000/")
        app.run(host='0.0.0.0', port=5000, debug=True)