# VSCode e PlatformIO
Abra E:\Infineon\Infineon.code-workspace, ou apenas E:\Infineon\firmware.
O platformio.ini fica em firmware, que é a raiz do projeto embarcado.
A extensão PlatformIO já foi encontrada instalada no computador do usuário.

## Firmware
A integração Arduino-Pico/Earle Philhower fornece SDK RP2040 e USB CDC ao PlatformIO.
A lógica I2C e de protocolo é compartilhada em firmware/main.c:
- CMake nativo: main() usa stdio USB do SDK;
- PlatformIO: src/main.cpp inclui o mesmo fonte, com setup()/loop() e Serial USB.
Não usar o core Arduino Mbed com esta configuração.
Consulte https://arduino-pico.readthedocs.io/en/stable/platformio.html

No VSCode use PlatformIO > Project Tasks > pico > Build.
Ou execute, na raiz:
powershell -File scripts/build-firmware.ps1
O primeiro build baixa plataforma, SDK e toolchain.
core_dir é local ao projeto (.pio-core), sem modificar pacotes globais.
O endereço Git segue o branch padrão; após primeiro build validado, fixe as
versões/commits para reprodução. Ainda não há build validado.
UF2 compilado é copiado para release/firmware/InfineonPico.uf2.
Nenhum script faz upload automático para hardware.

## Aplicativo Windows
powershell -File scripts/install-dependencies.ps1
powershell -File scripts/build-desktop.ps1
Resultado esperado: release/desktop/InfineonBench/InfineonBench.exe.
Distribuir a pasta InfineonBench inteira, não apenas o EXE.
O script exige testes lógicos e smoke gráfico antes do empacotamento.
F5 usa as configurações Python na pasta raiz.

## Rede
As tentativas nesta sessão falharam em files.pythonhosted.org (10054)
e TLS do PowerShell/cURL (SEC_E_NO_CREDENTIALS).
Não foi desabilitada a verificação de certificados.
Esses arquivos preparam o build, mas não comprovam que um UF2/EXE foi gerado.
