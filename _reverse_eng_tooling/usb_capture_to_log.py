#!/usr/bin/env python3
"""
usb_capture_to_log.py

Le uma captura .pcapng feita com Wireshark/USBPcap (Windows) e produz um
transcript de texto legivel do trafego de dados USB (bulk/interrupt IN e
OUT), no mesmo estilo de hexdump usado pelo serial_sniffer_relay.py --
facilitando comparar visualmente com os "magic strings" e "fingerprints"
ja conhecidos de outras familias de radios no CHIRP.

Requisitos:
    - Wireshark instalado (o executavel `tshark` precisa estar no PATH,
      ou informe o caminho completo com --tshark).
      No Windows costuma ficar em:
          C:\\Program Files\\Wireshark\\tshark.exe

Uso:
    python usb_capture_to_log.py captura.pcapng --device 4 -o transcript.log

    --device e o "usb.device_address" do adaptador serial, visivel no
    Wireshark ao clicar num pacote dele (campo "USB URB" -> "Device").
    Se omitido, o script tenta usar todos os dispositivos e avisa quando
    ha mais de um candidato com dados.

Convencao de direcao adotada no transcript:
    OUT (host -> dispositivo) = "APP->RADIO"  (o app enviando pro cabo)
    IN  (dispositivo -> host) = "RADIO->APP"  (o cabo/radio respondendo)
"""

import argparse
import shutil
import subprocess
import sys


def hexdump_line(data: bytes, width: int = 16) -> list[str]:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_part = ' '.join('%02x' % b for b in chunk)
        hex_part = hex_part.ljust(width * 3 - 1)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append('    %s  |%s|' % (hex_part, ascii_part))
    return lines


def find_tshark(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which('tshark')
    if found:
        return found
    # Caminhos comuns no Windows, caso nao esteja no PATH
    candidates = [
        r'C:\Program Files\Wireshark\tshark.exe',
        r'C:\Program Files (x86)\Wireshark\tshark.exe',
    ]
    for c in candidates:
        if shutil.which(c):
            return c
    raise FileNotFoundError(
        "Nao encontrei o 'tshark' no PATH. Use --tshark para indicar o "
        "caminho completo (ex.: --tshark \"C:\\Program Files\\Wireshark"
        "\\tshark.exe\")")


def extract_fields(tshark_path: str, pcap_path: str, device: str | None):
    display_filter = 'usb.capdata'
    if device:
        display_filter = 'usb.device_address == %s && usb.capdata' % device

    cmd = [
        tshark_path,
        '-r', pcap_path,
        '-Y', display_filter,
        '-T', 'fields',
        '-e', 'frame.time_relative',
        '-e', 'usb.device_address',
        '-e', 'usb.endpoint_address.direction',
        '-e', 'usb.capdata',
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('tshark falhou: %s' % proc.stderr.strip())
    return proc.stdout.splitlines()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('pcap', help='Arquivo .pcapng capturado no Wireshark')
    ap.add_argument('--device',
                    help='usb.device_address do adaptador serial '
                         '(veja no Wireshark). Se omitido, processa todos.')
    ap.add_argument('-o', '--output', default='usb_transcript.log',
                    help='Arquivo de transcript de saida')
    ap.add_argument('--tshark', default=None,
                    help='Caminho completo para tshark.exe, se nao '
                         'estiver no PATH')
    args = ap.parse_args()

    tshark_path = find_tshark(args.tshark)
    print('Usando tshark em: %s' % tshark_path)

    rows = extract_fields(tshark_path, args.pcap, args.device)
    if not rows:
        print('Nenhum pacote com dados encontrado. Confira o --device '
              '(usb.device_address) ou tente sem esse filtro para ver '
              'todos os dispositivos.')
        sys.exit(1)

    devices_seen = set()
    with open(args.output, 'w', encoding='utf-8') as out:
        out.write('# Transcript gerado a partir de %s\n' % args.pcap)
        out.write('# OUT (direction=0) = APP->RADIO (host envia)\n')
        out.write('# IN  (direction=1) = RADIO->APP (dispositivo responde)\n\n')

        for row in rows:
            parts = row.split('\t')
            if len(parts) < 4:
                continue
            ts, dev, direction, capdata = parts[0], parts[1], parts[2], parts[3]
            if not capdata:
                continue
            devices_seen.add(dev)
            try:
                data = bytes.fromhex(capdata.replace(':', ''))
            except ValueError:
                continue
            label = 'APP->RADIO' if direction == '0' else 'RADIO->APP'
            out.write('[%8s] dev=%s %s (%d bytes)\n' % (
                ts, dev, label, len(data)))
            for line in hexdump_line(data):
                out.write(line + '\n')

    print('Transcript salvo em %s' % args.output)
    if not args.device and len(devices_seen) > 1:
        print('Aviso: mais de um usb.device_address apareceu nos dados: '
              '%s -- rode novamente com --device <um destes> para '
              'isolar so o adaptador do cabo de programacao.' %
              ', '.join(sorted(devices_seen)))


if __name__ == '__main__':
    main()
