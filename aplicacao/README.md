# Novidades da versão 0.52

Gravar dump completo, na aba Parâmetros e gravação, copia a área USER de um dump para o controlador ligado e grava um slot. O trim e a área de fabricante deste CI permanecem os dele. Gravar somente parâmetros modificados grava só o que já foi alterado e aplicado em RAM. No IR3567B, os registradores 228 e 229 são zerados antes da cópia completa, como no ProgramComanche. O CI novo precisa responder como o modelo selecionado.

---

# Novidades da versão 0.51

Importar dump, na aba Parâmetros e gravação, não recusa o arquivo inteiro. Linhas inválidas e valores contraditórios são contados. Entram só os registradores que existem no JSON selecionado. Um valor sem regra de validação também entra e pode ser gravado depois. Havendo ocorrências, a tela pede confirmação e a gravação fica sob responsabilidade de quem confirmou. O parâmetro só é deixado de fora quando não há código único para gravar.

---

# Novidades da versão 0.50

O aplicativo usa o firmware de protocolo 16. Cada operação segue o JSON escolhido: leitura, telemetria, dump e gravação. Um perfil incompleto aparece como recusado e não entra na lista. O IR35217 é identificado no registrador FB. Os parâmetros editáveis respeitam a máscara de escrita do perfil. O ensaio antigo de RAM não é enviado a esse firmware.

Um Pico de protocolo anterior ainda se identifica. Gravação, recarga e habilitação pedem o protocolo 16.

---

# Novidades da versão 0.49

Gravar somente parâmetros modificados compara a RAM com a leitura feita antes da alteração. O valor 0 aplicado no código 26 deixa de ser recusado só porque o arquivo de exemplo já estava em FF.

---

# Novidades da versão 0.48

As listas fechadas do IR35217 que cabem na faixa USER usam a mesma escrita do IR3567B: o código entra nos bits do registrador, com o bit 7 à esquerda. Uma leitura da placa que não devolve o mapa do JSON escolhido, ou que devolve um registrador de fora desse mapa, mostra um alerta e não carrega os valores.

---

# Novidades da versão 0.47

Combo inicia em “Selecione o CI”. Parâmetros e leituras da placa esperam o modelo escolhido.

---

# Novidades da versão 0.46

Código centralizado, explicação dos campos somente leitura e troca de controlador sem manter a sessão anterior.

---

# Novidades da versão 0.45

Seleção para listas fechadas, coluna com o endereço hexadecimal do registrador e nova ordem das abas.

---

# Novidades da versão 0.44

Controladores em `controllers/*.json`. Interface removida. Porta serial só com nome e descrição básica.

---

# Novidades da versão 0.43

Tensão de saída: Linear16 + 50 mV, ou + 56,25 mV quando o ajuste é 0 mV.

---

# Novidades da versão 0.42

Tensão de saída é de novo o Linear16 do PMBus, sem somar o ajuste. Assim a tela acompanha a palavra lida.

---

# Novidades da versão 0.41

Gravação em RAM pede uma nova amostra de telemetria. O monitoramento não é esquecido por outra operação.

---

# Novidades da versão 0.40

JSON de relatório que já existe pede confirmação para substituir. Recusar grava outro nome.

---

# Novidades da versão 0.39

Tensão de saída: Linear16 corrigido por n×6,25 mV do ajuste. O código 8 soma 50 mV e acompanha o multímetro.

---

# Novidades da versão 0.38

Monitoramento só na aba Telemetria. A barra de progresso não fica em 100% por causa das amostras. A tensão de saída não soma o ajuste de tensão.

---

# Novidades da versão 0.37

Gráfico maior que a grade de amostras. A tabela de fases foi para Parâmetros e gravação, porque os limites são programados.

---

# Novidades da versão 0.36

Medições em colunas: entrada sobre a saída correspondente. Título VRM / BENCH removido para dar espaço à tabela de amostras. A aba Fases espera a leitura dos parâmetros.

---

# Novidades da versão 0.35

Gráficos novos: tensão e corrente de entrada, temperatura 2 e potência de entrada. A subdivisão Fases lista limites programados por fase, sem gráfico e sem alarme ao vivo.

---

# Novidades da versão 0.34

Operações demoradas no hardware, como leitura e gravação de parâmetros, usam o cursor de espera até o término. O monitoramento contínuo mantém o ponteiro normal.

---

# Novidades da versão 0.33

O aviso do checkbox Barramento conferido cita o checkbox. Leitura sem resposta do controlador abre uma caixa pedindo para confirmar se a placa está energizada, sem derrubar o Pico. Ícone próprio no executável e na barra de título. Religar saídas e recarregar a memória permanente continuam no diagnóstico.

---

# Novidades da versão 0.32

Confirmações usam Sim e Não. Ler placa não pede arquivo; Salvar leitura pede, com nome sugerido. Importar dump fica só em Parâmetros e gravação, onde o botão de limpar se chama Limpar valores. Endereços avançados ficam ocultos. Religar saídas, recarregar a memória permanente e Limpar log permanecem no diagnóstico.

---

# Novidades da versão 0.31

Catálogo do IR3567B ampliado para 44 campos, com as conversões que puderam ser conferidas. Firmware UF2 0.26 e protocolo 15 não mudaram.

Edição liberada, após teste de ida e volta e de preservação de bits: compensação de carga, sobrecorrente rápida e lenta, sobretensão e subtensão relativas, tensão máxima no ramo SVI, limiares acumulados de fase e tipo de driver. Código 0 da compensação de carga é exibido como 1 mΩ; gravar 1 mΩ usa o código linear. Sem fases no loop, a corrente fica somente leitura.

Somente leitura: quantidade de fases, modo Intel/MPOL/AMD/GPU e SVI1/SVI2. Modo da proteção de corrente e outros campos sem tabela oficial continuam sem conversão. Nenhum teste daqui avalia se o valor é eletricamente adequado à placa.

---

# Novidades da versão 0.30

Nome do aplicativo e executável: VRM Bench / VRMBench.exe. Mantenha a pasta _internal junto ao executável. A identificação técnica do protocolo do Pico foi preservada para compatibilidade; firmware não mudou.

- Grupo de conexão agora diz Conexão com Raspberry Pi Pico. Conectar ao Pico não representa confirmação do CI.
- Todas as operações da interface que acessam um Pico já conectado passam, no worker serializado, por observação de SDA/SCL e identificação PMBus com PEC. Uma falha impede iniciar a ação solicitada. Leituras e escritas também mantêm suas validações durante a operação. A checagem não mede fisicamente a alimentação nem elimina a possibilidade de desconexão posterior.
- Gráficos retêm os últimos 100 valores válidos de cada medição, com eixo por número de amostra, removendo automaticamente os antigos. Intervalo de coleta continua configurável, mas não determina espaçamento horizontal.
- Cartões mantêm o valor anterior durante a coleta e atualizam assim que cada resultado válido chega. Sem nova leitura confirmada, o último valor fica amarelo com explicação no tooltip; não é apresentado como medição nova.
- A tabela usa colunas fixadas pelo layout, sem redimensionar a cada linha, com pinturas agrupadas. As leituras continuam serializadas; não houve mudança no protocolo I²C para acelerar a operação. Resultados detalhados permanecem no histórico exportável.
- Ler placa e salvar dump pede destino antes da leitura e sugere dump_yyyy_mm_dd.txt. Cancelar não lê a placa. Leitura estável atualiza a tela e salva o TXT no destino escolhido, além da cópia automática de bancada. Falha no destino escolhido é informada sem descartar a leitura.

Validação: 165 testes automatizados e auto-teste do executável em simulação. Nenhum comando enviado à placa durante o desenvolvimento. Mantidas as limitações de conversões e de loop da versão anterior.

---

# VRM Bench 0.30

Interface reorganizada sobre os fontes da versão 0.28. Firmware: manter UF2 0.26, protocolo 15. Nenhuma modificação no protocolo, rotina do Pico ou firmware foi necessária.

## Fluxo

1. Conecte o Pico e confira o barramento. Nenhuma porta é aberta automaticamente.
2. Em Parâmetros e gravação, clique Ler valores atuais. Essa leitura também salva um dump estável em captures/dumps.
3. Os valores atuais são somente leitura. Digite apenas os novos valores desejados, em unidades humanas; vazio preserva o parâmetro. Campos amarelos são propostas, vermelhos têm erro. Aplicar em RAM mostra uma revisão e não gasta slot.
4. Para persistir, use Gravar permanentemente. O programa relê a imagem, consulta os slots, mostra o consumo e o saldo restante, e pede confirmação com Não como padrão. A imagem e os slots são conferidos novamente antes do envio. Não repete automaticamente uma gravação que falhou.

## Abas

- Telemetria: leitura individual ou periódica, intervalo configurável entre fim e início das coletas; Pausar conclui a amostra corrente, Cancelar leitura pede interrupção. Gráficos de tensão, temperatura, corrente e potência. Até 100 pontos por gráfico, 600 relatórios no histórico exportável. Valores ausentes nunca são tratados como zero. São medições da saída endereçada, sem troca de PAGE; não se atribui automaticamente uma leitura ao loop 2 ou a VCORE sem confirmação na placa.
- Parâmetros: 40 campos catalogados, separados entre Loop 1, Loop 2 e Compartilhados. Conversões confirmadas permitem editar tensão de partida e offset em modo AMD, frequência e limites térmicos. Outros campos permanecem somente leitura com indicação quando sua conversão não está validada. O catálogo não representa todos os campos internos do silício.
- Dump: mapa completo já suportado pela 0.28, 130 endereços (10–90 e B7), no formato de três colunas. Não inclui TRIM nem equivale a uma cópia bruta de toda a memória permanente.
- Diagnóstico e manutenção: logs, endereços avançados, religamento das saídas e recarga da memória permanente preservados.

## Validação de valores e importação

Aceita vírgula ou ponto decimal. Rejeita texto hexadecimal, infinito, NaN, valores fora da faixa e passos não representáveis. A frequência informa o valor realizável mais próximo em vez de arredondar silenciosamente. Offset mantém os bits do outro loop; duas propostas no mesmo registrador geram uma única escrita. Tensão de partida usa o ramo AMD, com passos de 0,0125 V e efeito na próxima partida (religamento separado na manutenção).

Importar TXT preenche somente propostas diferentes que tenham conversão validada; não substitui a leitura atual nem escreve automaticamente. O modo deve coincidir com o da placa; máscaras incompatíveis são rejeitadas. Diferenças fora dos campos editáveis são contadas na tela e não aplicadas. Não é um gravador irrestrito de dumps de outra placa.

A aplicação em RAM relê os bytes e dependências antes da primeira escrita, salva backup e usa a rotina PBYTE da 0.28. Uma falha interrompe o lote; alterações anteriores podem ter sido aplicadas. O estado é invalidado e exige releitura. A gravação permanente continua limitada à região USER pelo procedimento validado; a comparação prévia usa o arquivo PcYes fornecido na versão 0.28.

## Validação da entrega

Testes automatizados, auto-teste em simulação e revisão visual em janelas grande e reduzida. Nenhuma leitura/escrita física na placa durante o desenvolvimento. Os limites representam a codificação suportada, não uma avaliação de adequação elétrica de cada ajuste para a placa do usuário.
