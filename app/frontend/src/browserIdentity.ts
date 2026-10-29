type BrowserIdentity = {visitor_id:string;visitor_proof:string;fingerprint:string}

const sha256Initial = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
  0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]
const sha256Constants = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

function rotateRight(value:number, amount:number) {
  return (value >>> amount) | (value << (32 - amount))
}

// SHA-256 fallback for HTTP origins where browsers disable crypto.subtle.
function sha256Fallback(input:Uint8Array) {
  const bitLength = input.length * 8
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64
  const padded = new Uint8Array(paddedLength)
  padded.set(input)
  padded[input.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000))
  view.setUint32(paddedLength - 4, bitLength >>> 0)

  const hash = [...sha256Initial]
  const words = new Uint32Array(64)
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i++) words[i] = view.getUint32(offset + i * 4)
    for (let i = 16; i < 64; i++) {
      const x = words[i - 15], y = words[i - 2]
      const s0 = rotateRight(x, 7) ^ rotateRight(x, 18) ^ (x >>> 3)
      const s1 = rotateRight(y, 17) ^ rotateRight(y, 19) ^ (y >>> 10)
      words[i] = (words[i - 16] + s0 + words[i - 7] + s1) >>> 0
    }

    let [a, b, c, d, e, f, g, h] = hash
    for (let i = 0; i < 64; i++) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25)
      const choose = (e & f) ^ (~e & g)
      const temp1 = (h + sum1 + choose + sha256Constants[i] + words[i]) >>> 0
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22)
      const majority = (a & b) ^ (a & c) ^ (b & c)
      const temp2 = (sum0 + majority) >>> 0
      h = g; g = f; f = e; e = (d + temp1) >>> 0
      d = c; c = b; b = a; a = (temp1 + temp2) >>> 0
    }
    hash[0] = (hash[0] + a) >>> 0; hash[1] = (hash[1] + b) >>> 0
    hash[2] = (hash[2] + c) >>> 0; hash[3] = (hash[3] + d) >>> 0
    hash[4] = (hash[4] + e) >>> 0; hash[5] = (hash[5] + f) >>> 0
    hash[6] = (hash[6] + g) >>> 0; hash[7] = (hash[7] + h) >>> 0
  }
  return hash.map(word => word.toString(16).padStart(8, '0')).join('')
}

async function digest(text:string) {
  const input = new TextEncoder().encode(text)
  const subtle = globalThis.crypto?.subtle
  if (subtle) {
    const bytes = await subtle.digest('SHA-256', input)
    return [...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('')
  }
  return sha256Fallback(input)
}
function randomSecret() {
  return [...crypto.getRandomValues(new Uint8Array(32))].map(b=>b.toString(16).padStart(2,'0')).join('')
}
async function prepare():Promise<BrowserIdentity> {
  let fingerprint=localStorage.getItem('browserFingerprint')
  if (!fingerprint) {
    const canvas=document.createElement('canvas');canvas.width=220;canvas.height=30
    const context=canvas.getContext('2d')
    if(context) {context.font='16px Arial';context.fillText('AgentServe browser identity',2,20)}
    fingerprint=await digest(JSON.stringify({ua:navigator.userAgent,platform:navigator.platform,
      language:navigator.language,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
      colorDepth:screen.colorDepth,cores:navigator.hardwareConcurrency,canvas:canvas.toDataURL()}))
    localStorage.setItem('browserFingerprint',fingerprint)
  }
  let visitor=localStorage.getItem('visitorId')
  if (!visitor) {
    const seed=localStorage.getItem('browserIdentitySeed') || randomSecret()
    localStorage.setItem('browserIdentitySeed',seed)
    const hex=(await digest(fingerprint+':'+seed)).slice(0,32)
    visitor=`${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`
    localStorage.setItem('visitorId',visitor)
  }
  const proof=localStorage.getItem('visitorProof') || randomSecret()
  localStorage.setItem('visitorProof',proof)
  return {visitor_id:visitor,visitor_proof:proof,fingerprint}
}
export async function withBrowserIdentity<T>(action:(identity:BrowserIdentity)=>Promise<T>):Promise<T> {
  // Serialize across tabs as well as within this component to avoid two first visits.
  const run=async()=>action(await prepare())
  return navigator.locks ? navigator.locks.request('agentserve-browser-identity',run) : run()
}
