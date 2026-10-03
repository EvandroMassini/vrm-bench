# Evolução para gravação e referências
## IR35217
Implementar após leituras físicas estáveis e confirmação da revisão:
- conferir identidade, arquivo, região e estado de operação;
- capturar original e ler flags/ponteiros de programação;
- planejar diferenças; máscara de verificação não define máscara de escrita;
- implementar escrita RAM documentada e mudança do endereço quando aplicável;
- sequência MTP específica, timeout e verificação após reinicialização;
- preservar trim do CI de destino; não copiar ajustes individuais de outro chip.
Não há gravação habilitada em v0.1. Não há promessa de clonagem integral.
## IR3567B
Perfil separado. Não reutilizar mapa nem sequência Salem.
O resumo oficial confirma I2C/SMBus/PMBus e MTP, mas não contém protocolo completo.
A resposta oficial abaixo informa guia de programação sob NDA.
Suporte atual é somente transporte RAW experimental com endereço/registro informado.
## Fontes consultadas em 30/09/2026
- Salem TB0023 V1.2 (IR35217), apêndice A define máscara de verificação:
https://community.infineon.com/gfawx74859/attachments/gfawx74859/powermanagement/1930/2/TB0023%20Salem%20Programming%20Guide%20V1%202.pdf
- IR3567B product brief:
https://www.infineon.com/assets/row/public/documents/24/49/pb-ir3567b.pdf?fileId=5546d462533600a4015356803a7228ef
- Resposta Infineon sobre guia IR3567B:
https://community.infineon.com/t5/Power-Management-ICs/Technical-brief-note-for-IR3567B/td-p/1094114
- Pico SDK I2C:
https://www.raspberrypi.com/documentation/pico-sdk/hardware.html
- RP2040:
https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf
## Proveniência da amostra
TXT transcrito da mensagem do usuário, atribuído a MSI RX5700 7+1.
Sem identificação autenticada do CI ou comprovação da saída auxiliar.
São 132 entradas; nenhuma interpretação funcional dos bytes de fase foi presumida.
