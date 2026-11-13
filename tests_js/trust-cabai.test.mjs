import test from 'node:test';
import assert from 'node:assert/strict';
import {selTrustCabai, rincianTrustCabai, kolomTrustCabai} from '../site/assets/trust-cabai.js';

const trust = {versi:'cabai-v1',tanggal_penilaian:'2026-11-13',per_horizon:Object.fromEntries([1,7,30].map(h => [String(h),{
  level:h===7?'sedang':'belum_cukup_bukti',gagal:[],belum_dinilai:['Bukti belum cukup'],
  syarat:{sedang:[{syarat:'Sumber <img src=x onerror=alert(1)>',lolos:null}],tinggi:[]},
  arah:{level:'rendah',syarat:{sedang:[],tinggi:[]}},metrik:{sedang:{smape:8,bias:-3,n:12}}
}]))};

test('trust cabai menampilkan level per horizon tanpa memetakan persen lama',()=>{
  const html=selTrustCabai(trust);
  for(const h of [1,7,30])assert.match(html,new RegExp(`H\\+${h}`));
  assert.match(html,/Sedang/);assert.match(html,/Belum cukup bukti/);
  assert.doesNotMatch(html,/90%|80%/);
  assert.equal(selTrustCabai(null),'<span class="meta-kecil">-</span>');
});

test('rincian memisahkan arah dan harga, menampilkan alasan, dan mengamankan markup',()=>{
  const html=rincianTrustCabai(trust);
  assert.match(html,/Harga dan rentang/);assert.match(html,/Arah/);
  assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);
  assert.match(html,/Belum cukup bukti/);
});

test('ekspor menyimpan versi dan level eksplisit pada tiga horizon',()=>{
  const row=kolomTrustCabai(trust);
  assert.equal(row.versi_trust_cabai,'cabai-v1');assert.equal(row.trust_cabai_7,'sedang');
  assert.equal(row.trust_arah_cabai_7,'rendah');assert.equal(kolomTrustCabai(null).trust_cabai_7,'');
});

test('tingkat tinggi menampilkan metrik dari masa uji tinggi',()=>{
  const data=structuredClone(trust);
  data.per_horizon['7'].level='tinggi';
  data.per_horizon['7'].metrik.tinggi={smape:1.234,bias:.5,n:24};
  data.per_horizon['7'].arah.basis={tinggi:'ramalan_terbit_prospektif'};
  assert.match(rincianTrustCabai(data),/<td>7 hari<\/td>.*?1,23/s);
  assert.match(rincianTrustCabai(data),/arsip ramalan yang benar-benar diterbitkan/);
});
