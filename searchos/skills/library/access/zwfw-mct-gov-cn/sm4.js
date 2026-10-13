 /**
  * @title： 国密sm4
  * @description: 工具类-基于gm-crypt改造为适合无脚手架的js项目
  * @version: V1.0
  */

 /*使用
  *引入<script src="./sm4.js"></script> 
  * key:加解密秘钥（前后台对应） 
  * iv:cbc模式下需配置iv参数（iv：偏移量）
  * cbc加密 encrypt_cbc('加密内容', key, iv)
  * cbc解密 decrypt_cbc('解密内容', key, iv)
  * ecb加密 encrypt_ecb('加密内容', key)
  * ecb解密 decrypt_ecb('解密内容', key)
  */

  (function(r) {
    if (typeof exports === "object" && typeof module !== "undefined") {
        module.exports = r()
    } else if (typeof define === "function" && define.amd) {
        define([], r)
    } else {
        var e;
        if (typeof window !== "undefined") {
            e = window
        } else if (typeof global !== "undefined") {
            e = global
        } else if (typeof self !== "undefined") {
            e = self
        } else {
            e = this
        }
        e.base64js = r()
    }
})(function() {
    var r, e, t;
    return function r(e, t, n) {
        function o(i, a) {
            if (!t[i]) {
                if (!e[i]) {
                    var u = typeof require == "function" && require;
                    if (!a && u) return u(i, !0);
                    if (f) return f(i, !0);
                    var d = new Error("Cannot find module '" + i + "'");
                    throw d.code = "MODULE_NOT_FOUND", d
                }
                var c = t[i] = {
                    exports: {}
                };
                e[i][0].call(c.exports, function(r) {
                    var t = e[i][1][r];
                    return o(t ? t : r)
                }, c, c.exports, r, e, t, n)
            }
            return t[i].exports
        }
        var f = typeof require == "function" && require;
        for (var i = 0; i < n.length; i++) o(n[i]);
        return o
    }({
        "/": [function(r, e, t) {
            "use strict";
            t.byteLength = c;
            t.toByteArray = v;
            t.fromByteArray = s;
            var n = [];
            var o = [];
            var f = typeof Uint8Array !== "undefined" ? Uint8Array : Array;
            var i = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
            for (var a = 0, u = i.length; a < u; ++a) {
                n[a] = i[a];
                o[i.charCodeAt(a)] = a
            }
            o["-".charCodeAt(0)] = 62;
            o["_".charCodeAt(0)] = 63;

            function d(r) {
                var e = r.length;
                if (e % 4 > 0) {
                    throw new Error("Invalid string. Length must be a multiple of 4")
                }
                return r[e - 2] === "=" ? 2 : r[e - 1] === "=" ? 1 : 0
            }

            function c(r) {
                return r.length * 3 / 4 - d(r)
            }

            function v(r) {
                var e, t, n, i, a;
                var u = r.length;
                i = d(r);
                a = new f(u * 3 / 4 - i);
                t = i > 0 ? u - 4 : u;
                var c = 0;
                for (e = 0; e < t; e += 4) {
                    n = o[r.charCodeAt(e)] << 18 | o[r.charCodeAt(e + 1)] << 12 | o[r.charCodeAt(
                        e + 2)] << 6 | o[r.charCodeAt(e + 3)];
                    a[c++] = n >> 16 & 255;
                    a[c++] = n >> 8 & 255;
                    a[c++] = n & 255
                }
                if (i === 2) {
                    n = o[r.charCodeAt(e)] << 2 | o[r.charCodeAt(e + 1)] >> 4;
                    a[c++] = n & 255
                } else if (i === 1) {
                    n = o[r.charCodeAt(e)] << 10 | o[r.charCodeAt(e + 1)] << 4 | o[r.charCodeAt(e +
                        2)] >> 2;
                    a[c++] = n >> 8 & 255;
                    a[c++] = n & 255
                }
                return a
            }

            function l(r) {
                return n[r >> 18 & 63] + n[r >> 12 & 63] + n[r >> 6 & 63] + n[r & 63]
            }

            function h(r, e, t) {
                var n;
                var o = [];
                for (var f = e; f < t; f += 3) {
                    n = (r[f] << 16) + (r[f + 1] << 8) + r[f + 2];
                    o.push(l(n))
                }
                return o.join("")
            }

            function s(r) {
                var e;
                var t = r.length;
                var o = t % 3;
                var f = "";
                var i = [];
                var a = 16383;
                for (var u = 0, d = t - o; u < d; u += a) {
                    i.push(h(r, u, u + a > d ? d : u + a))
                }
                if (o === 1) {
                    e = r[t - 1];
                    f += n[e >> 2];
                    f += n[e << 4 & 63];
                    f += "=="
                } else if (o === 2) {
                    e = (r[t - 2] << 8) + r[t - 1];
                    f += n[e >> 10];
                    f += n[e >> 4 & 63];
                    f += n[e << 2 & 63];
                    f += "="
                }
                i.push(f);
                return i.join("")
            }
        }, {}]
    }, {}, [])("/")
});
const Sbox = [
    -42, -112, -23, -2, -52, -31, 61, -73, 22, -74, 20, -62, 40, -5, 44, 5, 43, 103, -102, 118, 42, -66, 4, -61, -86, 68, 19, 38, 73, -122, 6, -103, -100, 66, 80, -12, -111, -17, -104, 122, 51, 84, 11, 67, -19, -49, -84, 98, -28, -77, 28, -87, -55, 8, -24, -107, -128, -33, -108, -6, 117, -113, 63, -90, 71, 7, -89, -4, -13, 115, 23, -70, -125, 89, 60, 25, -26, -123, 79, -88, 104, 107, -127, -78, 113, 100, -38, -117, -8, -21, 15, 75, 112, 86, -99, 53, 30, 36, 14, 94, 99, 88, -47, -94, 37, 34, 124, 59, 1, 33, 120, -121, -44, 0, 70, 87, -97, -45, 39, 82, 76, 54, 2, -25, -96, -60, -56, -98, -22, -65, -118, -46, 64, -57, 56, -75, -93, -9, -14, -50, -7, 97, 21, -95, -32, -82, 93, -92, -101, 52, 26, 85, -83, -109, 50, 48, -11, -116, -79, -29, 29, -10, -30, 46, -126, 102, -54, 96, -64, 41, 35, -85, 13, 83, 78, 111, -43, -37, 55, 69, -34, -3, -114, 47, 3, -1, 106, 114, 109, 108, 91, 81, -115, 27, -81, -110, -69, -35, -68, 127, 17, -39, 92, 65, 31, 16, 90, -40, 10, -63, 49, -120, -91, -51, 123, -67, 45, 116, -48, 18, -72, -27, -76, -80, -119, 105, -105, 74, 12, -106, 119, 126, 101, -71, -15, 9, -59, 110, -58, -124, 24, -16, 125, -20, 58, -36, 77, 32, 121, -18, 95, 62, -41, -53, 57, 72
];
const CK = [
    462357, 472066609, 943670861, 1415275113, 1886879365, -1936483679, -1464879427, -993275175, -521670923, -66909679, 404694573, 876298825, 1347903077, 1819507329, -2003855715, -1532251463, -1060647211, -589042959, -117504499, 337322537, 808926789, 1280531041, 1752135293, -2071227751, -1599623499, -1128019247, -656414995, -184876535, 269950501, 741554753, 1213159005, 1684763257
];
const FK = [
    -1548633402, 1453994832, 1736282519, -1301273892
];

/**
 * 将字符串转为Unicode数组
 * @example "1234" => [49, 50, 51, 52];
 * @param {String} str 要转换的字符串
 * @returns {Number[]} 转换后的数组
 */
const stringToArray = (str) => {
    if (!/string/gi.test(Object.prototype.toString.call(str))) {
        str = JSON.stringify(str);
    }
    return unescape(encodeURIComponent(str)).split("").map(val => val.charCodeAt());
}

const rotateLeft = (x, y) => {
    return x << y | x >>> (32 - y);
}

const tauTransform = (a) => {
    return Sbox[a >>> 24 & 0xff] << 24 | Sbox[a >>> 16 & 0xff] << 16 | Sbox[a >>> 8 & 0xff] << 8 | Sbox[a & 0xff];
}

const tTransform1 = (z) => {
    let b = tauTransform(z);
    let c = b ^ rotateLeft(b, 2) ^ rotateLeft(b, 10) ^ rotateLeft(b, 18) ^ rotateLeft(b, 24);
    return c
}

/* const tTransform2 = (z) => {
    let b = tauTransform(z);
    let c = b ^ rotateLeft(b, 13) ^ rotateLeft(b, 23);
    return c
} */

const toByte = (value) => {
    console.log(value);
    
    if (value < -128 || value > 127) {
        throw new Error('Value out of range for byte type');
    }
    return value & 0xFF; // 计算 0-255 范围的值
}   

const PUT_ULONG_BE = (n, i) => {
    let b = new Array(4).fill(0); // 创建一个长度为 5 的数组并初始化为 0

    // 使用位运算提取每个字节
    b[0] = (n >> 24) & 0xFF; // 提取最高有效字节
    b[1] = (n >> 16) & 0xFF; // 提取次高有效字节
    b[2] = (n >> 8) & 0xFF;  // 提取次低有效字节
    b[3] = n & 0xFF;         // 提取最低有效字节

    // 将每个元素转为有符号的 byte 值
    for (let i = 0; i < b.length; i++) {
        if (b[i] > 127) {
            b[i] -= 256; // 处理从 128 到 255 的值，使其变为 -128 到 -1
        }
    }
    
    return b
} 

const sm4Sbox = (inch) => {
   let i = inch & 255;
   let retVal = Sbox[i];
    return retVal;
} 

const GET_ULONG_BE = (b, i) => {
    let n = (b[i] & 255) << 24 | (b[i + 1] & 255) << 16 | (b[i + 2] & 255) << 8 | b[i + 3] & 255 & -1;
    return n;
 } 

 const SHL = (x, n) => {
    return (x & -1) << n;
 } 

 const ROTL = (x, n) => {
    return SHL(x,n) | x >> 32 -n;
 } 

const tTransform2 = (ka) => {
    let bb = 0;
    let rk = 0;
    const b = [4];
    const a = PUT_ULONG_BE(ka, 0);
    
    b[0] = sm4Sbox(a[0]);
    b[1] = sm4Sbox(a[1]);
    b[2] = sm4Sbox(a[2]);
    b[3] = sm4Sbox(a[3]);
    bb = GET_ULONG_BE(b, 0);
    rk = bb ^ ROTL(bb, 13) ^ ROTL(bb, 23);
    return rk;
}

const EncryptRoundKeys = (key) => {
    const keys = [];
    const mk = [
        (key[0] & 255) << 24 | (key[1] & 255) << 16 | (key[2] & 255) << 8 | key[3] & 255 & -1,
        (key[4] & 255) << 24 | (key[5] & 255) << 16 | (key[6] & 255) << 8 | key[7] & 255 & -1,
        (key[8] & 255) << 24 | (key[9] & 255) << 16 | (key[10] & 255) << 8 | key[11] & 255 & -1,
        (key[12] & 255) << 24 | (key[13] & 255) << 16 | (key[14] & 255) << 8 | key[15] & 255 & -1,
    ];

    let k = new Array(36);
    k[0] = mk[0] ^ FK[0];
    k[1] = mk[1] ^ FK[1];
    k[2] = mk[2] ^ FK[2];
    
    let i = 0;
    for (k[3] = mk[3] ^ FK[3]; i < 32; i++) {
        k[i + 4] = k[i] ^ tTransform2(k[i + 1] ^ k[i + 2] ^ k[i + 3] ^ CK[i]);
        keys[i] = k[i + 4];
    }

    return keys;
}

const UINT8_BLOCK = 16;
const getChainBlock = (arr, baseIndex = 0) => {
    
    let block = [
        arr[baseIndex] << 24 | arr[baseIndex + 1] << 16 | arr[baseIndex + 2] << 8 | arr[baseIndex + 3],
        arr[baseIndex + 4] << 24 | arr[baseIndex + 5] << 16 | arr[baseIndex + 6] << 8 | arr[baseIndex + 7],
        arr[baseIndex + 8] << 24 | arr[baseIndex + 9] << 16 | arr[baseIndex + 10] << 8 | arr[baseIndex + 11],
        arr[baseIndex + 12] << 24 | arr[baseIndex + 13] << 16 | arr[baseIndex + 14] << 8 | arr[baseIndex + 15]
    ];
    return block;
}

const doBlockCrypt = (blockData, roundKeys) => {
    let xBlock = new Array(36);
    blockData.forEach((val, index) => xBlock[index] = val);
    // loop to process 32 rounds crypt
    for (let i = 0; i < 32; i++) {
        xBlock[i + 4] = xBlock[i] ^ tTransform1(xBlock[i + 1] ^ xBlock[i + 2] ^ xBlock[i + 3] ^ roundKeys[i]);
    }
    let yBlock = [xBlock[35], xBlock[34], xBlock[33], xBlock[32]];
    return yBlock;
}

const padding = (originalBuffer) => {
    if (originalBuffer === null) {
        return null;
    }
    let paddingLength = UINT8_BLOCK - originalBuffer.length % UINT8_BLOCK;
    let paddedBuffer = new Array(originalBuffer.length + paddingLength);

    originalBuffer.forEach((val, index) => paddedBuffer[index] = val);
    paddedBuffer.fill(paddingLength, originalBuffer.length);
    return paddedBuffer;
}

function isNotBlank(str) {
    return str !== null && str.trim() !== '';
}


const dePadding = (paddedBuffer) => {
    if (paddedBuffer === null) {
        return null;
    }
    let paddingLength = paddedBuffer[paddedBuffer.length - 1];
    let originalBuffer = paddedBuffer.slice(0, paddedBuffer.length - paddingLength);
    return originalBuffer;
}

const check = (name, str) => {
    if (!str || str.length != 16) {
        console.error(`${name} should be a 16 bytes string.`);
        return false;
    }
    return true;
}

/**
 * CBC加密模式
 * @example encrypt_cbc("1234", "1234567890123456", "1234567890123456") => "K++iI4IhSGMnEJZT/jv1ow=="
 * @param {any} plaintext 要加密的数据
 * @param {String} key 
 * @param {String} iv 
 * @param {String} mode base64 | "text"
 * @returns {String} 加密后的字符串
 */
const encrypt_cbc = (plaintext, key, iv, mode = "base64") => {
    if (!check("iv", iv) && !check("key", key)) {
        return;
    }

    let encryptRoundKeys = EncryptRoundKeys(stringToArray(key));
    let plainByteArray = stringToArray(JSON.stringify(plaintext));
    let padded = padding(plainByteArray);
    let blockTimes = padded.length / UINT8_BLOCK;
    let outArray = [];
    // init chain with iv (transform to uint32 block)
    let chainBlock = getChainBlock(stringToArray(iv));
    // console.log(padded, blockTimes, encryptRoundKeys, chainBlock);
    for (let i = 0; i < blockTimes; i++) {
        // extract the 16 bytes block data for this round to encrypt
        let roundIndex = i * UINT8_BLOCK;
        let block = getChainBlock(padded, roundIndex);
        // xor the chain block
        chainBlock[0] = chainBlock[0] ^ block[0];
        chainBlock[1] = chainBlock[1] ^ block[1];
        chainBlock[2] = chainBlock[2] ^ block[2];
        chainBlock[3] = chainBlock[3] ^ block[3];
        // use chain block to crypt
        let cipherBlock = doBlockCrypt(chainBlock, encryptRoundKeys);
        // make the cipher block be part of next chain block
        chainBlock = cipherBlock;
        for (let l = 0; l < UINT8_BLOCK; l++) {
            outArray[roundIndex + l] = cipherBlock[parseInt(l / 4)] >> ((3 - l) % 4 * 8) & 0xff;
        }
    }

    // cipher array to string
    if (mode === 'base64') {
        return base64js.fromByteArray(outArray);
    } else {
        // text
        return decodeURIComponent(escape(String.fromCharCode(...outArray)));
    }
}

const sm4Lt = (ka) => {
    let bb = 0;
    let c = 0;
    const b = [4];
    const a = PUT_ULONG_BE(ka, 0);
    b[0] = sm4Sbox(a[0]);
    b[1] = sm4Sbox(a[1]);
    b[2] = sm4Sbox(a[2]);
    b[3] = sm4Sbox(a[3]);
    bb = GET_ULONG_BE(b, 0);
    c = bb ^ ROTL(bb, 2) ^ ROTL(bb, 10) ^ ROTL(bb, 18) ^ ROTL(bb, 24);
    
    return c;
}

const sm4F = (x0, x1, x2, x3, rk) => {
    return x0 ^ sm4Lt(x1 ^ x2 ^ x3 ^ rk);
}

const sm4_one_round = (sk, input) => {
    let i = 0;
    const ulbuf = new Array(36).fill(0);
    ulbuf[0] = GET_ULONG_BE(input, 0);
    ulbuf[1] = GET_ULONG_BE(input, 4);
    ulbuf[2] = GET_ULONG_BE(input, 8);

    for(ulbuf[3] = GET_ULONG_BE(input, 12); i < 32; ++i) {
        ulbuf[i + 4] = sm4F(ulbuf[i], ulbuf[i + 1], ulbuf[i + 2], ulbuf[i + 3], sk[i]);
    }
    const byteArrays = [];
    byteArrays.push(PUT_ULONG_BE(ulbuf[35], 0));
    byteArrays.push(PUT_ULONG_BE(ulbuf[34], 4));
    byteArrays.push(PUT_ULONG_BE(ulbuf[33], 8));
    byteArrays.push(PUT_ULONG_BE(ulbuf[32], 12));
    // 初始化一个空数组，用于存储每次调用的结果
    const combinedArray = [];

    // 调用函数四次，收集每次返回的数组
    for (let i = 0; i < byteArrays.length; i++) {
        const array = byteArrays[i];
        combinedArray.push(...array); // 使用扩展运算符将当前数组元素添加到合并数组中
    }
    
    return combinedArray;
    
}

/**
 * ECB加密模式
 * @example encrypt_ebc("1234", "1234567890123456") => "woPrxebr8Xvyo1qG8QxAUA=="
 * @param {any} plaintext 要加密的数据
 * @param {String} key 
 * @param {String} mode base64 | "text"
 * @returns {String} 加密后的字符串
 */
const encrypt_ecb = (plaintext, key, mode = "base64") => {
    //console.log(plaintext, key)
    if (!check("key", key)) {
        return;
    }

    let encryptRoundKeys = EncryptRoundKeys(stringToArray(key));
    // let plainByteArray = stringToArray(JSON.stringify(plaintext));
    let plainByteArray = stringToArray(plaintext);
    let padded = padding(plainByteArray);
    let blockTimes = padded.length / UINT8_BLOCK;

    // 初始化一个空数组，用于存储每次调用的结果
    const outArray = [];
    for (let i = 1; i <= blockTimes; i++) {
        // extract the 16 bytes block data for this round to encrypt
        let roundIndex = i * UINT8_BLOCK;  
        const array = sm4_one_round(encryptRoundKeys, padded.slice(roundIndex-16,roundIndex));
        outArray.push(...array);
        
    }

    // cipher array to string
    if (mode === 'base64') {
        // return base64js.fromByteArray(outArray);
        let cipherText = btoa(String.fromCharCode.apply(null, new Uint8Array(outArray)))
        if (isNotBlank(cipherText)) {
            cipherText = cipherText.replaceAll(/\+/g, "@");
            cipherText = cipherText.replaceAll(/\r/g, "#");
            cipherText = cipherText.replaceAll(/\n/g, "!");
        }
        return cipherText;
    } else {
        // text
        return decodeURIComponent(escape(String.fromCharCode(...outArray)));
    }
}
/**
 * CBC解密模式
 * @example decrypt_cbc("K++iI4IhSGMnEJZT/jv1ow==", "1234567890123456", "1234567890123456") => "1234"
 * @param {any} plaintext 要解密的数据
 * @param {String} key 
 * @param {String} iv 
 * @param {String} mode base64 | "text"
 * @returns {String} 解密后的字符串
 */
const decrypt_cbc = (ciphertext, key, iv, mode = "base64") => {
    if (!check("iv", iv) && !check("key", key)) {
        return;
    }
    // get cipher byte array
    let cipherByteArray = null;
    let decryptRoundKeys = EncryptRoundKeys(stringToArray(key)).reverse();
    if (mode === 'base64') {
        // cipher is base64 string
        cipherByteArray = base64js.toByteArray(ciphertext);
    } else {
        // cipher is text
        cipherByteArray = stringToArray(ciphertext);
    }

    let blockTimes = cipherByteArray.length / UINT8_BLOCK;
    let outArray = [];

    // init chain with iv (transform to uint32 block)
    let chainBlock = getChainBlock(stringToArray(iv));
    //console.log(cipherByteArray, decryptRoundKeys, chainBlock)
    for (let i = 0; i < blockTimes; i++) {
        // extract the 16 bytes block data for this round to encrypt
        let roundIndex = i * UINT8_BLOCK;
        // make Uint8Array to Uint32Array block
        let block = getChainBlock(cipherByteArray, roundIndex);
        // reverse the round keys to decrypt
        let plainBlockBeforeXor = doBlockCrypt(block, decryptRoundKeys);
        // xor the chain block
        let plainBlock = [
            chainBlock[0] ^ plainBlockBeforeXor[0],
            chainBlock[1] ^ plainBlockBeforeXor[1],
            chainBlock[2] ^ plainBlockBeforeXor[2],
            chainBlock[3] ^ plainBlockBeforeXor[3]
        ];
        // make the cipher block be part of next chain block
        chainBlock = block;
        for (let l = 0; l < UINT8_BLOCK; l++) {
            outArray[roundIndex + l] = plainBlock[parseInt(l / 4)] >> ((3 - l) % 4 * 8) & 0xff;
        }
    }
    // depadding the decrypted data
    let depaddedPlaintext = dePadding(outArray);
    // transform data to utf8 string
    return JSON.parse(decodeURIComponent(escape(String.fromCharCode(...depaddedPlaintext))));
}
/**
 * ECB解密模式
 * @example decrypt_ecb("woPrxebr8Xvyo1qG8QxAUA==", "1234567890123456") => "1234"
 * @param {any} plaintext 要解密的数据
 * @param {String} key 
 * @param {String} mode base64 | "text"
 * @returns {String} 解密后的字符串
 */
const decrypt_ecb = (ciphertext, key, mode = "base64") => {
    if (!check("key", key)) {
        return;
    }
    if (isNotBlank(ciphertext)) {
        ciphertext = ciphertext.replaceAll(/@/g, "+");
        ciphertext = ciphertext.replaceAll(/#/g, "\r");
        ciphertext = ciphertext.replaceAll(/!/g, "\n");
    }
    // get cipher byte array
    let decryptRoundKeys = EncryptRoundKeys(stringToArray(key)).reverse();
    let cipherByteArray = null;
    if (mode === 'base64') {
        // cipher is base64 string
        // cipherByteArray = base64js.toByteArray(ciphertext);
        // 解码 Base64 字符串
        const decodedString = atob(ciphertext);

        // 将解码后的字符串转换回字节数组
        cipherByteArray = new Uint8Array(decodedString.length);
        for (let i = 0; i < decodedString.length; i++) {
            cipherByteArray[i] = decodedString.charCodeAt(i);
        }
        
    } else {
        // cipher is text
        cipherByteArray = stringToArray(ciphertext);
    }
    let blockTimes = cipherByteArray.length / UINT8_BLOCK;
    const outArray = [];

    for (let i = 1; i <= blockTimes; i++) {
        // extract the 16 bytes block data for this round to encrypt
        let roundIndex = i * UINT8_BLOCK;
        const array = sm4_one_round(decryptRoundKeys, cipherByteArray.slice(roundIndex-16,roundIndex));
        outArray.push(...array);
        
    }
    

    // depadding the decrypted data
    let depaddedPlaintext = dePadding(outArray);

    // transform data to utf8 string
    return bytesToString(depaddedPlaintext);
}

function bytesToString(bytes) {
    const textDecoder = new TextDecoder('utf-8');
    return textDecoder.decode(new Uint8Array(bytes));
}
