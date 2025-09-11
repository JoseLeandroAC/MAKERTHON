from flask import Flask, request, jsonify
from deepface import DeepFace
import numpy as np
import base64
import cv2
import os
import time
import logging

app = Flask(__name__)

# --- ALTERAÇÃO: CONFIGURAÇÕES CENTRALIZADAS ---
# Mude aqui para testar outros modelos ou métricas facilmente.
MODELO_RECONHECIMENTO = "Facenet"
METRICA_DISTANCIA = "euclidean_l2"
DETECTOR_ROSTO = "retinaface"

# O limite de distância para considerar um rosto como "conhecido".
# Valores menores são mais rigorosos. Para Facenet com euclidean_l2, um valor comum é por volta de 1.0.
# O seu valor de 0.65 é bem rigoroso, o que é bom para evitar falsos positivos.
LIMITE_CONFIANCA = 0.65

# Pasta que contém as imagens das pessoas conhecidas.
BANCO_DE_DADOS = "imagens_conhecidas"
# ---------------------------------------------------


# --- ALTERAÇÃO: PRÉ-CARREGAMENTO DOS MODELOS DE IA ---
# Isso carrega os modelos na memória uma única vez quando o servidor inicia,
# tornando cada requisição de reconhecimento muito mais rápida.
print("="*40)
print("INICIANDO SERVIDOR E CARREGANDO MODELOS DE IA...")
try:
    _ = DeepFace.build_model(MODELO_RECONHECIMENTO)
    _ = DeepFace.build_model(DETECTOR_ROSTO)
    print("Modelos carregados com sucesso!")
except Exception as e:
    logging.error(f"Erro crítico ao carregar modelos: {e}")
print("Servidor pronto para receber requisições.")
print("="*40)
# -------------------------------------------------------


@app.route('/reconhecer', methods=['POST'])
def reconhecer_rosto_api():
    try:
        dados_recebidos = request.get_json()
        if 'imagem' not in dados_recebidos:
            return jsonify({'status': 'erro', 'mensagem': 'Nenhuma imagem enviada'}), 400
            
        imagem_base64 = dados_recebidos['imagem']
        
        imagem_bytes = base64.b64decode(imagem_base64)
        imagem_np = np.frombuffer(imagem_bytes, np.uint8)
        frame = cv2.imdecode(imagem_np, cv2.IMREAD_COLOR)

        # Usamos 'extract_faces' para encontrar e alinhar o rosto primeiro.
        rostos_extraidos = DeepFace.extract_faces(
            img_path=frame, 
            detector_backend=DETECTOR_ROSTO,
            enforce_detection=False
        )

        # Se nenhum rosto for detectado no frame, retorna uma resposta clara.
        if not rostos_extraidos or rostos_extraidos[0]['confidence'] == 0:
            return jsonify({
                'status': 'sucesso', 
                'identidade': 'Nenhum rosto detectado', 
                'distancia': None
            })

        # Pega a imagem do primeiro rosto detectado (já recortado e alinhado).
        rosto_alinhado = rostos_extraidos[0]['face']

        # Usa 'find' para comparar o rosto extraído com o banco de dados.
        resultados_df = DeepFace.find(
            img_path=rosto_alinhado,
            db_path=BANCO_DE_DADOS,
            model_name=MODELO_RECONHECIMENTO,
            distance_metric=METRICA_DISTANCIA,
            enforce_detection=False # Já detectamos, não precisa fazer de novo
        )
        
        # --- ALTERAÇÃO: LOG DE DEBUG DETALHADO ---
        # Imprime no terminal do servidor a tabela de resultados do DeepFace.
        print("\n--- DEBUG DO SERVIDOR ---")
        if not resultados_df or resultados_df[0].empty:
            print("DeepFace não encontrou nenhuma correspondência no banco de dados.")
        else:
            print("DataFrame completo retornado pelo DeepFace:")
            print(resultados_df[0].to_markdown(index=False)) # .to_markdown() para formatar como tabela
        print("-------------------------\n")
        # ------------------------------------

        # Verifica se a lista de resultados e o primeiro DataFrame não estão vazios.
        if resultados_df and not resultados_df[0].empty:
            # Pega a correspondência mais próxima (primeira linha).
            distancia = resultados_df[0]['distance'][0]
            
            if distancia < LIMITE_CONFIANCA:
                caminho_identidade = resultados_df[0]['identity'][0]
                # Extrai o nome da pasta (ex: .../imagens_conhecidas/Nome_Pessoa/img.jpg)
                nome_pessoa = caminho_identidade.split(os.path.sep)[-2]
                
                resposta = {
                    'status': 'sucesso',
                    'identidade': nome_pessoa,
                    'distancia': float(distancia)
                }
            else:
                # O rosto é parecido com alguém, mas não o suficiente para ter certeza.
                resposta = {
                    'status': 'sucesso',
                    'identidade': 'Desconhecido',
                    'distancia': float(distancia)
                }
        else:
            # Nenhum rosto no banco de dados foi considerado próximo o suficiente.
            resposta = {
                'status': 'sucesso', 
                'identidade': 'Desconhecido', 
                'distancia': None
            }
        
        print(f"Enviando resposta final: {resposta}")
        return jsonify(resposta)
            
    except Exception as e:
        logging.exception("Ocorreu um erro na rota /reconhecer")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


@app.route('/adicionar_rosto', methods=['POST'])
def adicionar_rosto():
    try:
        dados = request.get_json()
        imagem_base64 = dados['imagem']
        nome_da_pessoa = dados['nome'].replace(" ", "_").strip()
        
        if not nome_da_pessoa:
            return jsonify({'status': 'erro', 'mensagem': 'Nome da pessoa não pode ser vazio'}), 400
            
        imagem_bytes = base64.b64decode(imagem_base64)
        
        caminho_pasta = os.path.join(BANCO_DE_DADOS, nome_da_pessoa)
        os.makedirs(caminho_pasta, exist_ok=True)
        
        timestamp = int(time.time())
        caminho_foto = os.path.join(caminho_pasta, f"{nome_da_pessoa}_{timestamp}.jpg")
        
        with open(caminho_foto, "wb") as f:
            f.write(imagem_bytes)
            
        # Limpa o cache de representações para forçar o recálculo
        cache_file = os.path.join(BANCO_DE_DADOS, "representations_facenet.pkl")
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"Cache '{cache_file}' removido.")

        return jsonify({'status': 'sucesso', 'mensagem': f'Rosto de {nome_da_pessoa} adicionado com sucesso!'})
        
    except Exception as e:
        logging.exception("Ocorreu um erro na rota /adicionar_rosto")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


if __name__ == '__main__':
    # Usar 'threaded=True' pode ajudar a lidar com múltiplas requisições, mas para IA, o gargalo é o CPU.
    app.run(host='0.0.0.0', port=5000)