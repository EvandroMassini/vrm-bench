# Infineon Bench 0.6 — preparação da captura de configuração

## Primeiro teste: mapear a interface direta

Atualize o Pico com `firmware/infineon-pico-v0.6.uf2` e abra `desktop/InfineonBench/InfineonBench.exe`, mantendo `_internal`. Desconecte o alvo durante a atualização do UF2. Os fontes completos estão em `source/`, incluindo `Infineon.code-workspace` e `firmware/platformio.ini`.

1. Conecte pelo aplicativo e confirme protocolo v6.
2. Perfil IR3567B, endereço individual **70**, velocidade 100 kHz. Preserve SDA/GP4, SCL/GP5, GND comum, pullups 3,3 V e alimentação própria da placa. Verifique barramento de mestre único.
3. Abra a aba **Registradores ativos** e clique **Mapear interface I²C (ler D6)**.
4. Exporte como `interface_70.json` e salve o log.

Esse teste lê MFR_MODEL e D6 com PEC; não escreve D6 nem acessa automaticamente o endereço retornado. Segundo a referência de família, bit7 indica habilitação da interface direta e bits6:0 indicam seu endereço. O resultado ajudará a esclarecer a relação entre 08 e 70.

## Captura de registradores selecionados

O mecanismo foi implementado, mas ainda requer teste físico e uma lista documentada para o IR3567B. Deixe os campos vazios até termos essa lista. Não reutilize o dump IR35217 da RX5700 como mapa do IR3567B.

Na aba Registradores ativos, informe até 64 endereços de registrador HEX separados por espaços, a origem documental da lista e sua verificação. A lista não admite intervalos automáticos. O botão de captura executa duas passagens e compara os bytes; cancelar ou qualquer erro preserva resultados parciais. As passagens não são simultâneas: dados de estado podem mudar legitimamente. Igualdade não comprova completude, persistência nem ausência de registros protegidos.

Cada acesso envia SET_POINTER D3, endereço do registrador e PEC, terminando com STOP; depois lê GET_POINTER D4 com PEC. D3 modifica o ponteiro volátil de leitura, não grava um valor no registrador selecionado. Isso é diferente de uma transação estritamente passiva. As fases de seleção/endereço/PEC têm erros distintos. D0/D5 (escrita de configuração), desbloqueio, seleção de PAGE e comandos MTP não foram adicionados.

O JSON registra modelo, origem da lista, endereços solicitados, duas passagens, bytes, PEC, diferenças e STATUS_CML antes/depois. É uma **captura parcial dos registradores ativos**, não um backup completo da configuração e não uma leitura direta da memória MTP. Não é exportado um TXT de programação com máscaras inventadas.

## O que falta para um backup restaurável

- Mapa específico do IR3567B, com regiões, registros reservados/protegidos e máscaras.
- Verificar a leitura D3/D4 no alvo e comparar os dados com uma referência confiável.
- Distinguir valores ativos, ajustes de fabricação e configuração persistente; comparação após desligar/ligar pode ajudar, mas não prova acesso direto à MTP.
- Obter o procedimento de programação específico antes de qualquer escrita persistente.

Uma configuração exportada do IR3567B por ferramenta conhecida ou seu guia de programação pode fornecer a lista inicial. Não é necessário que seja a mesma placa para estudar o formato, mas valores de outra placa não devem ser gravados nesta.

## Referências e limites

O documento International Rectifier IR3565B V1.07, tabela 63, descreve D3 SET_POINTER, D4 GET_POINTER e D6 SET_I2C; a tabela também enumera o IR3567B entre os modelos da família. Usamos esse caminho como implementação experimental, sem presumir o mapa interno do IR3565B no IR3567B.

- [Reprodução do documento do fabricante](https://dtsheet.com/doc/1275065/ir3565b---international-rectifier)
- [PDF do fabricante espelhado](https://files.gitter.im/ethereum-mining/ethminer/znuw/ir3565b.pdf)
- [Infineon: guia específico IR3567B sujeito a NDA](https://community.infineon.com/t5/Power-Management-ICs/Technical-brief-note-for-IR3567B/td-p/1094114)

As figuras do Process Call D1 não foram obtidas com clareza suficiente para implementar seu enquadramento; não adivinhamos os bytes dessa alternativa. A documentação pública consultada não estabelece uma região completa de backup IR3567B.

Protocolo v6: `TEL 70 D6` lê D6; `REG 70 RR` seleciona o registrador RR via D3 e o lê via D4, sempre com PEC. HELLO retorna `OK INFINEON-PICO 6 READONLY`; READONLY significa sem escrita de configuração, admitindo alteração do ponteiro de leitura. A nova captura não foi validada no hardware; os testes de interface usam simulação.

Contexto de bancada informado pelo usuário: RX580 PcYes sem GPU, fora de computador. Telemetria VCORE confirmada em aproximadamente 1,1 V. A correspondência física dos sensores e a calibração de corrente/potência continuam pendentes.
