# Protocolo USB v2
ASCII, LF; CR ignorado. Uma solicitação pendente por vez. CDC 115200.
HELLO -> OK INFINEON-PICO 2 READONLY
READ aa rr -> OK vv
PROBE aa -> OK ACK | OK NACK

Endereços aa: 08..77, excluindo 0C; campos exatamente dois dígitos HEX.
PROBE usa GPIO open-drain por direção: nunca força nível alto.
O periférico I2C é restaurado após a transação. Clock nominal <=100kHz,
delay mínimo de 5us por fase; tolera alongamento de SCL até timeout de 25ms.
Erros: ERR BUS_BUSY, ERR BUS_CONFLICT, ERR SCL_TIMEOUT,
ERR I2C_POINTER, ERR I2C_READ, ERR BUS_LOW, ERR COMMAND, ERR LENGTH.
A busca é coordenada pelo PC com comandos PROBE individuais; pode cancelar entre eles.
Endereço sem ACK não é erro; timeout/conflito interrompe a busca.
READ continua usando I2C direto, não MFR_READ_REG do PMBus.
Nenhum comando de escrita de dados, desbloqueio ou programação MTP.
Sem log persistente no Pico. O aplicativo registra comandos/respostas após cada
operação, e permite salvar a sessão. Não emite texto assíncrono no USB.
Firmware v1 é reconhecido pelo aplicativo, mas não pode executar PROBE.
