import requests
import base64
import cv2
import time
import threading
from datetime import datetime

# URL da sua API
url_reconhecer = "http://127.0.0.1:5000/reconhecer"

# Iniciar a câmera
webcam = cv2.VideoCapture(0)

# Variáveis compartilhadas
last_face_info = None
last_text_info = 'Pressione ESPACO para reconhecer'
cor = (255, 255, 0)
processando = False
frame_para_processar = None

# Função para registrar a presença
def registrar_presenca(nome_pessoa, status):
    agora = datetime.now()
    data_e_hora = agora.strftime("%d-%m-%Y %H:%M:%S")
    with open("registro_presenca.txt", "a") as arquivo:
        arquivo.write(f"Nome: {nome_pessoa} | Status: {status} | Horario: {data_e_hora}\n")
    print(f"Presença de {nome_pessoa} registrada no arquivo.")

# Função de processamento em thread
def processar_frame_ia():
    global last_face_info, last_text_info, cor, processando, frame_para_processar
    
    while True:
        if frame_para_processar is not None:
            frame_temp = frame_para_processar
            frame_para_processar = None
            
            print("\n> Enviando imagem para a API para reconhecimento...")

            _, buffer = cv2.imencode('.jpg', frame_temp)
            imagem_base64 = base64.b64encode(buffer).decode('utf-8')
            dados = {'imagem': imagem_base64}

            try:
                resposta = requests.post(url_reconhecer, json=dados)
                
                if resposta.status_code == 200:
                    resultado = resposta.json()
                    status = resultado.get("status", "erro")
                    nome = resultado.get("identidade", "Desconhecido")
                    distancia = resultado.get("distancia")
                    facial_area = resultado.get("facial_area")

                    if facial_area:
                        last_face_info = facial_area
                    else:
                        last_face_info = None
                    
                    if status == "sucesso":
                        if nome != "Nenhum rosto detectado" and nome != "Desconhecido" and distancia is not None:
                            porcentagem = (1 - distancia) * 100
                            last_text_info = f"{nome} ({porcentagem:.1f}%)"
                            cor = (0, 255, 0)
                            registrar_presenca(nome, "Reconhecido")
                        else:
                            last_text_info = f"Desconhecido"
                            if distancia is not None:
                                porcentagem = (1 - distancia) * 100
                                last_text_info += f" ({porcentagem:.1f}%)"
                            cor = (0, 0, 255)
                            registrar_presenca("Desconhecido", "Nao Reconhecido")
                    else:
                        last_text_info = 'Erro na API'
                        cor = (0, 0, 255)
                        last_face_info = None
                else:
                    last_text_info = f'Erro HTTP: {resposta.status_code}'
                    cor = (0, 0, 255)
                    last_face_info = None
            except requests.exceptions.ConnectionError:
                last_text_info = 'Erro de conexao com a API'
                cor = (0, 0, 255)
                last_face_info = None
            
            processando = False
            
        time.sleep(0.1)

# Thread de processamento
thread_ia = threading.Thread(target=processar_frame_ia, daemon=True)
thread_ia.start()

print("A câmera está aberta. Pressione ESPACO para reconhecer um rosto ou 'q' para sair.")

while True:
    ret, frame = webcam.read()
    if not ret:
        break
    
    if last_face_info:
        x, y, w, h = last_face_info['x'], last_face_info['y'], last_face_info['w'], last_face_info['h']
        cv2.rectangle(frame, (x, y), (x + w, y + h), cor, 2)
        cv2.putText(frame, last_text_info, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, cor, 2)
    else:
        cv2.putText(frame, last_text_info, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, cor, 2)
    
    cv2.imshow('Reconhecimento Facial', frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord(' '):
        if not processando:
            processando = True
            last_text_info = 'Processando...'
            cor = (255, 165, 0)
            frame_para_processar = frame.copy()
    elif key == ord('q'):
        break

webcam.release()
cv2.destroyAllWindows()
