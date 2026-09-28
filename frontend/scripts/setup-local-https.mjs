import { spawnSync } from 'node:child_process'
import { randomBytes, randomUUID } from 'node:crypto'
import { chmodSync, copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { isIP } from 'node:net'
import { networkInterfaces } from 'node:os'
import { fileURLToPath } from 'node:url'

const directory = fileURLToPath(new URL('../../.local/https/', import.meta.url))
const publicCertificate = fileURLToPath(new URL('../public/intrac-local-ca.cer', import.meta.url))
const suppliedAddresses = process.argv.slice(2)
const addresses = suppliedAddresses.length ? suppliedAddresses : Object.values(networkInterfaces())
  .flat().filter(address => address && !address.internal && address.family === 'IPv4').map(address => address.address)
if (addresses.some(address => isIP(address) !== 4)) throw new Error('Supply IPv4 addresses only.')
const certificateAddresses = [...new Set(['127.0.0.1', ...addresses])]

process.umask(0o077)
mkdirSync(directory, { recursive: true, mode: 0o700 })
chmodSync(directory, 0o700)

function openssl(...args) {
  const result = spawnSync('openssl', args, { cwd: directory, encoding: 'utf8' })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(result.stderr || 'OpenSSL failed.')
}

const hasCa = existsSync(`${directory}ca.pem`)
const hasCaKey = existsSync(`${directory}ca-key.pem`)
if (hasCa !== hasCaKey) throw new Error('The local certificate authority is incomplete. Restore its matching certificate and key before continuing.')
if (!hasCa) {
  openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '365',
    '-keyout', 'ca-key.pem', '-out', 'ca.pem', '-subj', '/CN=InTrac Local Development CA',
    '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
    '-addext', 'keyUsage=critical,keyCertSign,cRLSign', '-addext', 'subjectKeyIdentifier=hash')
}
openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-sha256',
  '-keyout', 'server-key.pem', '-out', 'server.csr', '-subj', '/CN=InTrac Local Development')
writeFileSync(`${directory}server.ext`, [
  'basicConstraints=critical,CA:FALSE',
  'keyUsage=critical,digitalSignature,keyEncipherment',
  'extendedKeyUsage=serverAuth',
  `subjectAltName=DNS:localhost,${certificateAddresses.map(address => `IP:${address}`).join(',')}`,
  'subjectKeyIdentifier=hash', 'authorityKeyIdentifier=keyid,issuer', '',
].join('\n'))
openssl('x509', '-req', '-in', 'server.csr', '-CA', 'ca.pem', '-CAkey', 'ca-key.pem',
  '-set_serial', `0x${randomBytes(16).toString('hex')}`, '-out', 'server.pem',
  '-days', '90', '-sha256', '-extfile', 'server.ext')
openssl('verify', '-CAfile', 'ca.pem', 'server.pem')
openssl('x509', '-in', 'ca.pem', '-outform', 'DER', '-out', 'intrac-local-ca.cer')
copyFileSync(`${directory}intrac-local-ca.cer`, publicCertificate)
chmodSync(publicCertificate, 0o644)
const publicProfile = fileURLToPath(new URL('../public/intrac-local-ca.mobileconfig', import.meta.url))
writeFileSync(publicProfile, `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>PayloadType</key><string>Configuration</string>
  <key>PayloadVersion</key><integer>1</integer>
  <key>PayloadIdentifier</key><string>local.intrac.https</string>
  <key>PayloadUUID</key><string>${randomUUID()}</string>
  <key>PayloadDisplayName</key><string>InTrac Local Development CA</string>
  <key>PayloadOrganization</key><string>InTrac</string>
  <key>PayloadDescription</key><string>Installs the local InTrac certificate authority for HTTPS testing. After installation, enable full trust in Certificate Trust Settings.</string>
  <key>PayloadRemovalDisallowed</key><false/>
  <key>PayloadContent</key><array><dict>
    <key>PayloadType</key><string>com.apple.security.root</string>
    <key>PayloadVersion</key><integer>1</integer>
    <key>PayloadIdentifier</key><string>local.intrac.https.root</string>
    <key>PayloadUUID</key><string>${randomUUID()}</string>
    <key>PayloadDisplayName</key><string>InTrac Local Development CA</string>
    <key>PayloadCertificateFileName</key><string>intrac-local-ca.cer</string>
    <key>PayloadContent</key><data>${readFileSync(publicCertificate).toString('base64')}</data>
  </dict></array>
</dict></plist>
`)
chmodSync(publicProfile, 0o644)
console.log('Local HTTPS certificates ready. No device trust settings were changed.')
console.log('Start with npm run dev:https. Install and trust only intrac-local-ca.cer on each test device.')
for (const address of addresses) console.log(`App: https://${address}:5174 | iPhone profile: http://${address}:5173/intrac-local-ca.mobileconfig | Other devices: http://${address}:5173/intrac-local-ca.cer`)
