# Infineon Bench 0.4 — diagnóstico do acesso ao IR3567B

## Arquivos e atualização

- Firmware: `firmware/infineon-pico-v0.4.uf2`, para Pico original RP2040.
- Aplicativo: `desktop/InfineonBench/InfineonBench.exe`. Manter toda a pasta `_internal` junto.
- Fontes e VS Code: `source/Infineon.code-workspace`; PlatformIO: `source/firmware/platformio.ini`.
- Validação: `validation/`; testes da interface são simulados, não resultados da RX580.

Atualize ambos. Desconecte o alvo durante a atualização; entre em BOOTSEL, solte o botão e copie o UF2. O monitor serial deve responder a HELLO com `OK INFINEON-PICO 4 READONLY`. Feche o monitor antes de conectar pelo aplicativo.

## O que sabemos

O usuário observou ACK em 08 e 70 e NACK no comando MFR_ID em 70. Isso indica reconhecimento da fase de endereço, mas não identifica fabricante/modelo nem confirma que o ponto seja a interface de configuração desejada. Responder somente quando a placa está alimentada também não confirma essa identidade. Endereços neste programa são sempre de 7 bits: 70 gera E0 na fase de escrita e E1 na fase de leitura. Não digitar E0 como endereço.

## Primeiro roteiro na RX580

1. Conecte GP4 (pino 6) ao SDA, GP5 (pino 7) ao SCL e GND (por exemplo, pino 8) ao GND da placa. A placa utiliza sua alimentação; não conecte o 3,3 V do Pico à placa alimentada. Pullups devem estar em 3,3 V.
2. Selecione Pico USB, a COM correta e Conectar. Confirme protocolo v4.
3. Clique **Observar SDA/SCL**. Salve o resultado. Ele mostra amostras baixas e mudanças durante aproximadamente 100 ms, sem enviar clocks/comandos. Não mede tensão nem decodifica tráfego; pode perder pulsos curtos. Linhas altas não provam ausência de outro mestre. Atividade ou linha presa baixa exige investigar o barramento antes dos acessos ativos.
4. Verifique as condições elétricas e a ausência de outro mestre ativo, e marque a caixa correspondente. A implementação não é multimaster.
5. Em **Endereços HEX**, na seção Diagnóstico em sequência, deixe `08 70`. Esse campo é separado do endereço individual da primeira linha.
6. Comece com **100 kHz**, apenas **99 MFR_ID** marcado, PEC desmarcado e STOP intermediário desmarcado. Clique **Executar sequência**. Cada tentativa gera uma linha no log; NACK não desconecta o USB.
7. Exporte o resultado JSON com um nome próprio, por exemplo `rx580-08-70-100k-mfrid.json`. O botão Exportar salva o último resultado; salve antes de começar outro teste. O log mantém o histórico da sessão.
8. Sem erros de barramento, compare o mesmo teste em **50 kHz** e **10 kHz**, salvando separadamente. Velocidades são nominais: a implementação GPIO tem overhead e aceita clock stretching.
9. Para ampliar a busca, clique **Todos 08–77 (exceto 0C)**, mantenha apenas MFR_ID e execute. Essa busca envia MFR_ID diretamente, mesmo se o endereço não apareceu no teste ACK; não depende de um pre-scan. São 111 endereços, não incluindo chamadas gerais e endereços reservados mais baixos/altos. NACK de endereço ou comando é registrado e a busca continua. Não há repetição infinita.
10. Volte aos endereços candidatos (`08 70`, ou os que responderem) e marque também **98 PMBUS_REVISION**, **9A MFR_MODEL** e **9B MFR_REVISION**. Execute e exporte. Esses são formatos PMBus padronizados; o suporte pelo IR3567B ainda não foi confirmado. Bytes recebidos não provam por si só que a interface seja PMBus.

## Alternativas que a versão disponibiliza

| Opção | Quando ajuda | Limite |
|---|---|---|
| Busca ACK | Encontrar dispositivos que reconheçam endereço + W | Não identifica CI; equivale a Quick Command em alguns dispositivos |
| MFR_ID dirigido ou em sequência | Procurar resposta de identificação no barramento | NACK não demonstra ausência do IR3567B |
| PMBUS_REVISION / MFR_MODEL / MFR_REVISION | Comparar outros comandos padronizados | Suporte no alvo ainda desconhecido |
| 100/50/10 kHz | Investigar sensibilidade à temporização | Não corrige conexão, protocolo ou mestre concorrente |
| PEC opcional | Verificar CRC de uma resposta que suporte PEC | Não resolve NACK no comando; byte extra sem suporte pode ser inválido |
| STOP intermediário | Comparar leitura com STOP + novo START | Experimental, não é o Block Read PMBus padrão; sem PEC. Não corrige NACK ocorrido antes do STOP |
| Ler registrador | Leitura individual de 1 byte pelo periférico I2C do RP2040 | Usar registrador documentado; mapa IR35217 não vale automaticamente para IR3567B |
| Ler RAW GPIO | Leitura individual de 1 ou 2 bytes por software, sem byte de contagem | Informar endereço individual e registrador; usa velocidade e STOP selecionados; sem PEC e sem interpretação de endian/unidades |
| Observar SDA/SCL | Detectar níveis baixos/atividade amostrada | Não substitui multímetro, osciloscópio ou analisador lógico |

As opções não são automaticamente combinadas: selecione a variante e salve um relatório por teste para comparar uma variável de cada vez. Os comandos experimentais enviam o seletor antes de ler; não são captura passiva. Não há escrita de bytes de configuração, mudança de PAGE, CLEAR_FAULTS, desbloqueio, gravação MTP ou varredura automática 00–FF. Leituras RAW só devem ser escolhidas com documentação: registradores desconhecidos podem ter efeitos de leitura.

O endereço individual, com rótulo visível no topo à direita, é usado pelos botões Ler fabricante PMBus, Ler registrador e Ler RAW GPIO. A lista Endereços HEX é usada exclusivamente por Executar sequência. Usar ACKs encontrados copia a lista da última busca. Todos apenas preenche o campo; nada é transmitido até executar.

## Interpretar falhas

- PMBUS_ADDR_W: endereço + escrita rejeitado.
- PMBUS_COMMAND: endereço aceito, seletor de comando rejeitado (caso anterior em 70).
- PMBUS_ADDR_R: comando aceito, fase de endereço + leitura rejeitada.
- PMBUS_COUNT: contagem recebida fora de 1..32; firmware envia NACK/STOP. Pode ser formato incompatível, não prova defeito.
- PEC inválido: bytes recebidos não passaram na verificação; relatório não conta isso como resposta válida.
- BUS_BUSY / BUS_CONFLICT / SCL_TIMEOUT / PMBUS_TIMEOUT: teste interrompido; investigar sinais/concorrência, não repetir em massa.
- Resposta serial incompleta: transporte interrompido; reconectar o USB. NACK de alvo, por outro lado, agora preserva a conexão.

Cancelar preserva as tentativas concluídas e encerra entre transações; a transação em andamento tem prazo limitado. Erros fatais também preservam os resultados da sequência. Relatórios distinguem SIMULAÇÃO de Pico USB. O nome de modelo escolhido no aplicativo não autentica o dispositivo.

## Se nenhuma alternativa identificar o CI

O próximo dado útil será uma captura física SDA/SCL para conferir ACKs, níveis, tempos de subida, bytes enviados e presença de outro mestre. Um analisador lógico conhecido pode fazer isso; o segundo Pico pode futuramente ser dedicado a essa função com firmware apropriado, mas essa versão não inclui um analisador lógico ou emulador do alvo. Outra opção é comparar com um adaptador Infineon funcional e obter o guia de programação específico. Teste fora da placa exigirá um circuito de alimentação e desacoplamento baseado na documentação, não apenas ligar 3,3 V em um pino.

Ainda não há garantia de leitura da configuração, telemetria calibrada ou gravação do IR3567B. O objetivo desta versão é produzir evidências para escolher o protocolo correto. Não é uma emulação USB005 compatível com PowIRCenter.

## Protocolo serial v4

Comandos ASCII terminados em LF; respostas terminadas em CRLF. Mantidos HELLO, PROBE, READ e MID.

- `SPEED 64`, `SPEED 32`, `SPEED 0A`: 100, 50 e 10 kHz respectivamente (parâmetro HEX).
- `LINES`: 10.000 amostras digitais, aproximadamente 100 ms. Retorna contadores SDA baixo, SCL baixo, mudanças e estado final (bit0 SDA, bit1 SCL).
- `PM 70 99 00 00`: endereço, comando (98..9B), PEC (00/01), STOP intermediário (00/01). PEC+STOP é rejeitado.
- `RAW 70 RR 01 00`: RR é um registrador documentado; comprimento 01 ou 02; último parâmetro STOP. Não enviar literalmente RR.
- Bloco: `OK BLOCK NN DADOS PEC` (PEC `--` quando não solicitado). Para PMBUS_REVISION e RAW, NN é informado pelo firmware, não lido do barramento. Para MFR_ID/MODEL/REVISION o alvo fornece a contagem.

## Referências e validação

- [Infineon PowIRCenter, seção 23](https://www.infineon.com/assets/row/public/documents/24/42/an-0035.pdf): busca I2C por ACK e busca PMBus por MFR_ID.
- [PMBus Part II](https://pmbus.org/wp-content/uploads/2021/04/PMBus_Specification_Part_II_Rev_1-1_20070205.pdf): formatos de identificação padronizados, sem afirmar suporte específico no IR3567B.
- [Infineon: guia IR3567B](https://community.infineon.com/t5/Power-Management-ICs/Technical-brief-note-for-IR3567B/td-p/1094114): documentação de programação sujeita a NDA.

Testes automatizados verificam transporte, PEC, parâmetros, cancelamento, continuação após NACK e interrupção após falhas. O autoteste gráfico usa simulação. UF2 compilado para RP2040; nova transação elétrica ainda requer validação física no alvo. Fontes: C/C++ no Pico e Python/PySide6 no Windows.
