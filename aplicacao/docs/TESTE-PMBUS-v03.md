# Teste PMBus — versão 0.3

Esta versão acrescenta uma leitura dirigida de MFR_ID (comando 0x99), com protocolo SMBus Block Read e PEC opcional. Não grava configuração ou memória não volátil. A transação envia o código do comando antes de ler o bloco; não é uma leitura passiva.

## Primeiro teste na RX580

1. Desconecte os fios do alvo durante a atualização do Pico. Entre em BOOTSEL, solte o botão e copie firmware/infineon-pico-v0.3.uf2. A unidade deve desaparecer e surgir a porta COM.
2. Abra desktop/InfineonBench/InfineonBench.exe mantendo a pasta _internal junto dele. Feche outros monitores seriais.
3. Identifique o Pico e conecte. Deve aparecer protocolo v3. No monitor, HELLO retorna OK INFINEON-PICO 3 READONLY.
4. Mantenha GP4/SDA, GP5/SCL e GND comum. O alvo deve ter sua própria alimentação, pullups em 3,3 V e barramento sem outro mestre ativo. Não ligue a saída 3,3 V do Pico à placa alimentada. Uma placa funcionando não garante barramento exclusivo.
5. Confirme as condições do barramento na interface. Digite 70 no campo de endereço (7 bits, hexadecimal), candidato que respondeu no teste anterior. Não é identificação confirmada.
6. Deixe PEC desmarcado e clique Ler fabricante PMBus. Não há busca automática deste comando em outros endereços.
7. Salve o log e exporte o resultado JSON. O texto retornado informa somente o campo fabricante, não confirma modelo nem mapa de registradores.

Falhas PMBUS_ADDR_W/ADDR_R indicam NACK na fase indicada; PMBUS_COMMAND indica NACK no comando; PMBUS_COUNT indica contagem fora de 1..32; BUS_BUSY/CONFLICT e SCL_TIMEOUT indicam falha de barramento. PEC inválido impede aceitar a resposta. Não repetir automaticamente com PEC ou em 0x08: primeiro analisar o log. Uma falha não prova que o dispositivo não seja IR3567B.

## Validação e limites

Testes automatizados cobrem descoberta, DTR, enquadramento serial, parser de bloco, CRC-8 e compatibilidade com firmware antigo. O autoteste da interface usa dados simulados. A nova transação elétrica ainda precisa ser validada no alvo, idealmente com analisador lógico. Não implementamos monitoramento calibrado ou gravação RAM/MTP sem documentação específica do IR3567B.

O firmware usa sinais open-drain por software, tempo limite de clock e prazo global. Requer barramento de mestre único; a verificação de nível ocioso não substitui essa condição. Sem PEC não há validação CRC da resposta; os limites de comprimento continuam verificados.

## Referências

- Infineon PowIRCenter, seção 23: Scan PMBus usa MFR_ID para procurar controladores: https://www.infineon.com/assets/row/public/documents/24/42/an-0035.pdf
- PMBus Part II, comando MFR_ID 0x99, formato Block: https://pmbus.org/wp-content/uploads/2021/04/PMBus_Specification_Part_II_Rev_1-1_20070205.pdf
- Documentação específica IR3567B sujeita a NDA: https://community.infineon.com/t5/Power-Management-ICs/Technical-brief-note-for-IR3567B/td-p/1094114

## Compilação

Abra source/Infineon.code-workspace no VS Code. O projeto PlatformIO está em source/firmware/platformio.ini. Use o ambiente pico. Para desktop, instale requirements-build.txt e compile com PyInstaller usando InfineonBench.spec; este contém a correção de empacotamento ICU do Windows.
