# Primeiro teste: controlador soldado na placa
## Barramento correto
SVD/SVC normalmente designam os sinais de dados/clock SVI entre GPU e regulador.
Não são sinônimos de SDA/SCL. O guia Salem distingue SV_DIO/SV_CLK de SM_DIO/SM_CLK.
Este firmware usa a interface I2C de configuração. Confirme no esquema/boardview
ou por continuidade com a placa DESENERGIZADA os pontos que chegam a SM_DIO/SM_CLK.
Não há indicação universal de posição dos pads numa RX5700 ou RX580.
Não fornecemos números de pino do CI sem validar encapsulamento e revisão.

## Pico original
| Pico | Pino físico | Destino após confirmação |
|---|---|---|
| GP4 | 6 | SDA / SM_DIO por adaptação elétrica se necessária |
| GP5 | 7 | SCL / SM_CLK por adaptação elétrica se necessária |
| GND | 8 | GND comum |
Nenhuma ligação de VBUS, VSYS ou 3V3 à alimentação da placa nesta etapa.
Não ligar sinais com o alvo desenergizado e pull-ups ativos: risco de retroalimentação.
GPIO RP2040 não tolera 5V. Barramento abaixo de 3,3V pode exigir conversor bidirecional
open-drain adequado. Verifique pull-ups existentes e níveis com multímetro/osciloscópio.
O firmware deixa pull-ups internos desligados; a interface exige pull-ups externos adequados.
Ligue/desligue os cabos com fontes desligadas; defina alimentação do controlador pelo esquema.
Não presuma que alimentar apenas 3,3V num ponto da GPU seja aceitável.
Não altere EN/ADDR_PROT com base em nomes sem verificar o circuito.

## Sequência
1. Primeiro teste o aplicativo em simulação.
2. Compile/carregue firmware; sem alvo, HELLO confirma a porta USB.
3. Confirme alimentação, terra, sinais e ausência de outro mestre ativo.
   Placa energizada não implica barramento livre; firmware não arbitra com GPU.
4. Informe endereço I2C direto conhecido, em 7 bits. Nenhum padrão é assumido.
5. IR35217: uma leitura de FB pode ajudar a identificar a família Salem; o guia
   enumera vários IDs, mas não fornece nesta rotina associação exclusiva ao IR35217.
   Não aceitar um ACK isolado como identificação.
6. Leia USER/MFR, exporte JSON e repita. Compare registradores estáticos.
   Cada erro invalida a captura e fecha o transporte para impedir respostas atrasadas.
7. Leia B5, B6, B8 individualmente no IR35217 apenas após validar comunicação.
   Preserve os valores brutos; não interprete B6/B8 como contadores binários simples.
8. Para monitoramento futuro, selecionar apenas registradores de telemetria documentados;
   leituras arbitrárias podem ter efeitos como limpar estados.
Nenhum teste acima grava MTP. Selecionar o registrador via fase I2C de escrita é
parte da leitura; não equivale a gravar um valor de configuração.

## Fora da placa (etapa posterior)
Usar adaptador QFN compatível, alimentação regulada/limitada, desacoplamento e
terminações exigidas pelo guia do modelo. Não é apenas conectar três fios ao CI solto.
Validar pinagem e terminação antes de aplicar energia. A interface USB/I2C será reutilizada.

## Segundo Pico
Reservado para futuro emulador I2C de bancada, para testar falhas e respostas.
A v0.1 inclui simulação no PC, não firmware de emulador nem teste físico entre Picos.
