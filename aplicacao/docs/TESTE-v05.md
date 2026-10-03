# Infineon Bench 0.5 — estado e telemetria com PEC

## Primeiro teste

1. Atualize o Pico original RP2040 com `firmware/infineon-pico-v0.5.uf2` via BOOTSEL, com os fios do alvo desconectados durante a atualização.
2. Abra `desktop/InfineonBench/InfineonBench.exe`, mantendo `_internal` ao lado. Feche o monitor serial. Conecte em modo Pico USB; deve aparecer protocolo v5.
3. Use o perfil IR3567B e digite **70 no Endereço individual (HEX), no topo à direita**. A lista de endereços de diagnóstico não é usada por telemetria.
4. Preserve as conexões GP4/SDA, GP5/SCL e GND comum. A placa possui alimentação própria e pullups em 3,3 V; não conectar sua alimentação à saída 3,3 V do Pico. Verifique ausência de outro mestre ativo antes de marcar a caixa do barramento.
5. Selecione 100 kHz e clique **Ler telemetria (PEC)**. Este botão usa uma lista fixa de leituras; não precisa marcar os comandos 98/99/9A/9B. PEC é obrigatório e o formato é repeated START, independentemente das caixas de diagnóstico.
6. Veja a aba Telemetria e salve `telemetria_70.json` por Exportar resultado. Salve também o log. Primeiro avalie a captura individual.
7. Para acompanhar variações, **Monitorar 10 amostras (PEC)** faz dez capturas com pausa de 1 segundo entre elas. **Cancelar operação** interrompe entre transações e preserva resultados parciais. O intervalo total também inclui o tempo de leitura.

## Leituras e interpretação

A coleta começa verificando MFR_MODEL com PEC. Exige o código 44h; qualquer outro resultado interrompe o procedimento. Esse código é compatível com IR3567B segundo a tabela de identificação da família na referência abaixo; não autentica fisicamente o componente.

São lidos CAPABILITY, VOUT_MODE, STATUS_BYTE/WORD, STATUS_TEMPERATURE/CML/MFR_SPECIFIC e READ_VIN/IIN/VOUT/IOUT/TEMPERATURE_1/TEMPERATURE_2/POUT/PIN. Os códigos e comprimentos ficam em uma lista permitida no firmware; não há escrita de dados de configuração. Cada byte/word usa PEC, incluindo endereço, comando e dados na verificação.

Os words são preservados como bytes na ordem recebida, e interpretados com byte menos significativo primeiro. A referência de família descreve Linear11 para telemetria e Linear16 para VOUT; o expoente de VOUT é lido de VOUT_MODE. Quando o modo não é Linear ou sua leitura falha, VOUT permanece RAW. As escalas precisam ser verificadas na placa, por exemplo comparando VIN/VOUT com multímetro. Não há confirmação de calibração de corrente ou potência.

Os estados aparecem em hexadecimal, sem diagnóstico automático de defeito. STATUS_CML é lido antes e depois da série: tentativas anteriores com comandos rejeitados podem deixar flags registradas. O programa não limpa falhas. NACK no comando é registrado e não é repetido nos ciclos seguintes da mesma sessão; falha de PEC, endereço ou barramento interrompe a coleta. As leituras restantes de uma captura não são simultâneas.

Não se altera PAGE nem se atribui automaticamente a saída a VDDC ou VDDCI. Temperaturas têm rótulos do comando, não de sensores físicos confirmados. A versão não faz gravação RAM/MTP nem dump de configuração. Para entender os recursos de diagnóstico anteriores, consulte TESTE-v04.md.

## Evidência de identificação e limites da referência

O datasheet **International Rectifier IR3565B, V1.07, 4/2/2014, tabela 63, páginas 53–56**, inclui expressamente IR3567B na lista de identificação: modelo 44h. Foi consultada sua reprodução textual indexada, pois o download do PDF espelhado não concluiu nesta sessão.

- [Documento original espelhado pela Arrow](https://static6.arrow.com/aropdfconversion/25d4204dc63dce1a70386bfddca4e9964855b27f/679ir3565b.pdf)
- [Reprodução do documento do fabricante](https://dtsheet.com/doc/1275065/ir3565b---international-rectifier)
- [Resumo oficial IR3567B](https://www.infineon.com/assets/row/public/documents/24/49/pb-ir3567b.pdf): confirma disponibilidade de telemetria.
- [PMBus Part II](https://pmbus.org/wp-content/uploads/2022/01/PMBus-Specification-Rev-1-3-1-Part-II-20150313.pdf): protocolo e formatos padrão.

Há uma ambiguidade na descrição de tamanho do bloco MFR_MODEL da referência: ela menciona dois bytes e enumera 01h seguido do modelo. Nos testes físicos do usuário, o firmware recebeu contagem 01h e payload 44h, com PEC válido. Mantivemos o formato comprovado no alvo, sem forçar dois bytes de payload ou extrapolar o mapa proprietário de configuração do IR3565B para o IR3567B.

## Validação e desenvolvimento

UF2 compilado para RP2040; aplicativo empacotado com a correção de DLL ICU. Os testes automatizados incluem CRC de byte/word, sinal do Linear11, expoente do VOUT, modelo incompatível, comandos não suportados, cancelamento e interrupção por PEC inválido. O autoteste gráfico usa simulação; telemetria real da RX580 ainda não foi validada nesta versão.

Fontes: `source/Infineon.code-workspace`, com `source/firmware/platformio.ini`. Scripts de compilação em `source/scripts/`. O novo comando serial é `TEL 70 8B` (endereço e comando em HEX, final LF). PEC é sempre solicitado; o comprimento é definido pela lista permitida, não por um parâmetro arbitrário. Comandos antigos foram mantidos; HELLO agora retorna `OK INFINEON-PICO 5 READONLY`.
