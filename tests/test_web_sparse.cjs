// Oracle uses reduced fractions decoded from binary64 bits, not the checker’s
// canonical-hex parser or common integer scale. Only small test fixtures use
// dense matrices; the shipped sparse checker never expands CSR.
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const abs = n => n < 0n ? -n : n;
function gcd(a,b) {a=abs(a);b=abs(b);while(b)[a,b]=[b,a%b];return a;}
function f(n,d=1n) {if(d<0n){n=-n;d=-d;}const g=gcd(n,d);return [n/g,d/g];}
const add=(a,b)=>f(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);
const neg=a=>[-a[0],a[1]];
const sub=(a,b)=>add(a,neg(b));
const mul=(a,b)=>f(a[0]*b[0],a[1]*b[1]);
const div=(a,b)=>f(a[0]*b[1],a[1]*b[0]);
const absolute=a=>[abs(a[0]),a[1]];
const cmp=(a,b)=>a[0]*b[1]<b[0]*a[1]?-1:a[0]*b[1]>b[0]*a[1]?1:0;
const out=a=>({numerator:String(a[0]),denominator:String(a[1])});
function bits(value) {const view=new DataView(new ArrayBuffer(8));view.setFloat64(0,value,false);return view.getBigUint64(0,false);}
function hex(value) {const raw=bits(value),negative=raw>>63n?'-':'',e=Number((raw>>52n)&2047n),fraction=raw&((1n<<52n)-1n);if(e===0&&fraction===0n)return negative+'0x0.0p+0';const p=e===0?-1022:e-1023;return `${negative}0x${e===0?'0':'1'}.${fraction.toString(16).padStart(13,'0')}p${p>=0?'+':''}${p}`;}
function fraction(value) {const raw=bits(value),e=Number((raw>>52n)&2047n);let n=raw&((1n<<52n)-1n);if(e!==0)n+=1n<<52n;if(raw>>63n)n=-n;const p=(e===0?-1022:e-1023)-52;return p<0?f(n,1n<<BigInt(-p)):f(n<<BigInt(p));}
function document(A,b,x,w,decision=null) {const indptr=[0],indices=[],data=[];for(const row of A){row.forEach((v,j)=>{if(v!==0){indices.push(j);data.push(hex(v));}});indptr.push(data.length);}return {format:'certloom-sparse-dd-v1',A:{dimension:A.length,indptr,indices,data},b:b.map(hex),x:x.map(hex),weights:w.map(hex),decision:decision===null?null:{index:decision.index,above:hex(decision.above)}};}
function reference(A0,b0,x0,w0,decision) {
  const A=A0.map(r=>r.map(fraction)),b=b0.map(fraction),x=x0.map(fraction),w=w0.map(fraction),n=A.length;
  const gaps=[],residual=[];
  for(let i=0;i<n;i++) {
    let gap=mul(absolute(A[i][i]),w[i]),dot=f(0n);
    for(let j=0;j<n;j++){dot=add(dot,mul(A[i][j],x[j]));if(i!==j)gap=sub(gap,mul(absolute(A[i][j]),w[j]));}
    gaps.push(gap);residual.push(sub(b[i],dot));
  }
  const minimum=gaps.reduce((a,b)=>cmp(a,b)<0?a:b);
  const result={status:'not_certified',dimension:n,method:'weighted-diagonal-dominance',nonzeros:A0.reduce((s,r)=>s+r.filter(v=>v!==0).length,0),minimum_gap:out(minimum)};
  if(cmp(minimum,f(0n))<=0){result.reason='The recomputed weighted diagonal-dominance gap is not strictly positive in every row; this method cannot certify the solution.';return result;}
  const tau=residual.map((r,i)=>div(absolute(r),gaps[i])).reduce((a,b)=>cmp(a,b)>0?a:b);
  const radii=w.map(value=>mul(value,tau)),bounds=x.map((v,i)=>({lower:sub(v,radii[i]),upper:add(v,radii[i])}));
  result.status='certified';result.tau=out(tau);result.radii=radii.map(out);result.enclosures=bounds.map(v=>({lower:out(v.lower),upper:out(v.upper)}));
  if(decision!==null){const v=bounds[decision.index],above=fraction(decision.above);result.decision={index:decision.index,above:out(above),status:cmp(v.lower,above)>0?'above':cmp(v.upper,above)<=0?'not_above':'undecidable',lower:out(v.lower),upper:out(v.upper)};}
  return result;
}
// Independent exact Gaussian elimination checks actual solution containment,
// including nonsymmetric matrices and negative diagonal entries.
function solve(A,b) {const rows=A.map((r,i)=>[...r.map(fraction),fraction(b[i])]),n=rows.length;for(let c=0;c<n;c++){let p=c;while(p<n&&rows[p][c][0]===0n)p++;assert.ok(p<n);[rows[c],rows[p]]=[rows[p],rows[c]];const pivot=rows[c][c];for(let j=c;j<=n;j++)rows[c][j]=div(rows[c][j],pivot);for(let i=0;i<n;i++)if(i!==c){const factor=rows[i][c];for(let j=c;j<=n;j++)rows[i][j]=sub(rows[i][j],mul(factor,rows[c][j]));}}return rows.map(r=>r[n]);}

(async()=>{
  const {verifyText,VerificationError}=await import(pathToFileURL(path.resolve(__dirname,'../web/verify.mjs')));
  const checks=[];let oracleSystems=0;
  function check(name,fn){fn();checks.push(name);}
  function matches(A,b,x,w,decision=null){const actual=verifyText(JSON.stringify(document(A,b,x,w,decision)));assert.deepEqual(actual,reference(A,b,x,w,decision));oracleSystems++;if(actual.status==='certified'){const solution=solve(A,b);solution.forEach((v,i)=>{const interval=actual.enclosures[i],lower=f(BigInt(interval.lower.numerator),BigInt(interval.lower.denominator)),upper=f(BigInt(interval.upper.numerator),BigInt(interval.upper.denominator));assert.ok(cmp(lower,v)<=0&&cmp(v,upper)<=0);});}return actual;}
  const refuses=text=>assert.throws(()=>verifyText(text),VerificationError);
  const base=()=>document([[2,-1],[4,-3]],[1,-2],[0.25,-0.5],[1,1.5]);
  check('mixed-sign nonsymmetric weighted certificate and exact solution',()=>matches([[2,-1],[4,-3]],[1,-2],[0.25,-0.5],[1,1.5],{index:1,above:-0.5}));
  check('missing diagonals, empty rows, zero gap and negative gap refuse without singular claim',()=>{
    for(const A of [[[0]],[[0,1],[1,1]],[[1,1],[-1,1]],[[1,2],[0,1]]]){const n=A.length,result=matches(A,Array(n).fill(1),Array(n).fill(0),Array(n).fill(1),{index:0,above:0});assert.equal(result.status,'not_certified');for(const k of ['tau','radii','enclosures','decision','q','eta','radius'])assert.equal(Object.hasOwn(result,k),false);assert.doesNotMatch(result.reason,/singular/);}
  });
  check('strict threshold lower equality, upper equality, positive and negative subnormal offsets',()=>{
    assert.equal(matches([[1]],[2],[1],[1],{index:0,above:0}).decision.status,'undecidable');
    assert.equal(matches([[1]],[2],[1],[1],{index:0,above:2}).decision.status,'not_above');
    assert.equal(matches([[1]],[2],[1],[1],{index:0,above:-Number.MIN_VALUE}).decision.status,'above');
    assert.equal(matches([[1]],[2],[2],[1],{index:0,above:2}).decision.status,'not_above');
    assert.equal(matches([[1]],[2],[2],[1],{index:0,above:1}).decision.status,'above');
  });
  check('subnormal weights and overflowing floating dominance products remain exact',()=>{
    let result=matches([[Number.MIN_VALUE]],[Number.MIN_VALUE],[0],[Number.MIN_VALUE]);assert.deepEqual(result.radii,[out(f(1n))]);assert.deepEqual(result.tau,out(f(1n<<1074n)));assert.deepEqual(result.minimum_gap,out(f(1n,1n<<2148n)));
    result=matches([[Number.MAX_VALUE]],[Number.MAX_VALUE],[0],[Number.MAX_VALUE]);assert.deepEqual(result.radii,[out(f(1n))]);
    matches([[-Number.MAX_VALUE]],[Number.MIN_VALUE],[Number.MAX_VALUE],[Number.MIN_VALUE],{index:0,above:0});
  });
  check('common positive weight rescaling preserves every radius and enclosure',()=>{
    const one=matches([[2,-1],[4,-3]],[1,-2],[0.25,-0.5],[1,1.5]);const two=matches([[2,-1],[4,-3]],[1,-2],[0.25,-0.5],[2,3]);assert.deepEqual(one.radii,two.radii);assert.deepEqual(one.enclosures,two.enclosures);
  });
  check('80 deterministic dyadic systems agree with rational oracle and exact solves',()=>{
    let seed=912347;const next=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
    for(let trial=0;trial<80;trial++){const n=1+next()%6,w=Array.from({length:n},()=>2**(next()%3)),A=Array.from({length:n},()=>Array.from({length:n},()=>((next()%9)-4)/16));for(let i=0;i<n;i++){let sum=0;for(let j=0;j<n;j++)if(j!==i)sum+=Math.abs(A[i][j])*w[j];A[i][i]=(trial%2?-1:1)*(1+sum/w[i]);}matches(A,Array.from({length:n},()=>((next()%31)-15)/8),Array.from({length:n},()=>((next()%31)-15)/8),w,{index:next()%n,above:((next()%11)-5)/4});}
  });
  check('strict CSR dimensions, monotone rows and unique ordered coordinates',()=>{
    const mutations=[d=>d.A.dimension=0,d=>d.A.dimension=4097,d=>d.A.dimension=true,d=>d.A.dimension='2',d=>d.A.indptr=[0,2],d=>d.A.indptr=[1,2,4],d=>d.A.indptr=[0,3,2],d=>d.A.indptr=[0,2,3],d=>d.A.indices=[0,0,0,1],d=>d.A.indices=[1,0,0,1],d=>d.A.indices[0]=-1,d=>d.A.indices[0]=2,d=>d.A.indices[0]=true,d=>d.A.indices[0]=9007199254740992,d=>d.A.data.pop(),d=>d.A.data[0]=hex(0),d=>d.A.data[0]=hex(-0),d=>d.A.extra=1,d=>d.extra=1,d=>delete d.weights,d=>d.weights=[hex(1)],d=>d.b=[1,2],d=>d.x={},d=>d.decision={index:0,above:hex(1),extra:true}];
    for(const mutate of mutations){const d=base();mutate(d);refuses(JSON.stringify(d));}
    for(const key of ['dimension','indptr','indices']){const text=JSON.stringify(base());const old=key==='dimension'?'"dimension":2':key==='indptr'?'"indptr":[0':'"indices":[0';for(const replacement of key==='dimension'?['"dimension":2.0','"dimension":2e0']:key==='indptr'?['"indptr":[0.0','"indptr":[0e0']:['"indices":[0.0','"indices":[0e0','"indices":[9007199254740993'])refuses(text.replace(old,replacement));}
  });
  check('positive finite canonical weights are mandatory, even when matrix fails',()=>{
    for(const value of [hex(0),hex(-0),hex(-1),'nan','inf','0x1.0p+0','0x1.0000000000000p+00',true,1,null]){const d=base();d.weights[0]=value;refuses(JSON.stringify(d));}
    const d=document([[0]],[1],[0],[-1]);refuses(JSON.stringify(d));
  });
  check('duplicate decoded keys, unexpected fields and noncanonical coefficients refuse',()=>{
    let text=JSON.stringify(base());refuses(text.replace('"format":','"format":"certloom-sparse-dd-v1","format":'));refuses(text.replace('"dimension":2','"dimension":2,"\\u0064imension":2'));
    for(const bad of ['+0x1.0000000000000p+0','0x1.0000000000000p-0','0x1.0000000000000p+1024','0x1.0000000000000p-1023','0x0.0000000000000p-1022','0x0.0000000000001p-1021','0X1.0000000000000p+0','NaN','Infinity','1+1']){const d=base();d.A.data[0]=bad;refuses(JSON.stringify(d));}
    for(const index of [true,0.5,-1,2,'0',null]){const d=base();d.decision={index,above:hex(1)};refuses(JSON.stringify(d));}
  });
  check('4096 rows accepted without dense expansion',()=>{
    const n=4096,d={format:'certloom-sparse-dd-v1',A:{dimension:n,indptr:Array.from({length:n+1},(_,i)=>i),indices:Array.from({length:n},(_,i)=>i),data:Array(n).fill(hex(1))},b:Array(n).fill(hex(1)),x:Array(n).fill(hex(1)),weights:Array(n).fill(hex(1)),decision:null};const result=verifyText(JSON.stringify(d));assert.equal(result.status,'certified');assert.equal(result.nonzeros,n);assert.equal(result.enclosures.length,n);assert.ok(result.radii.every(v=>v.numerator==='0'&&v.denominator==='1'));
  });
  check('32768 nonzeros and more than40000 JSON nodes accepted; larger arrays rejected',()=>{
    const n=1024,indptr=[0],indices=[],data=[];for(let i=0;i<n;i++){for(let j=Math.floor(i/32)*32;j<Math.floor(i/32)*32+32;j++){indices.push(j);data.push(hex(i===j?2:1/1024));}indptr.push(data.length);}const d={format:'certloom-sparse-dd-v1',A:{dimension:n,indptr,indices,data},b:Array(n).fill(hex(0)),x:Array(n).fill(hex(0)),weights:Array(n).fill(hex(1)),decision:null};assert.equal(data.length,32768);assert.equal(verifyText(JSON.stringify(d)).status,'certified');d.A.data.push(hex(1));d.A.indices.push(0);d.A.indptr[n]++;refuses(JSON.stringify(d));
  });
  check('UTF8, nesting and100000-node caps preserved alongside dense40000 guard',()=>{
    refuses('"'+'é'.repeat(1024*1024)+'"');refuses(' '.repeat(2*1024*1024+1));refuses('['.repeat(10)+'0'+']'.repeat(10));refuses('{"format":"certloom-sparse-dd-v1","junk":['+'0,'.repeat(100000)+'0]}');
    assert.throws(()=>verifyText('{"format":"certloom-linear-v1","junk":['+'0,'.repeat(40000)+'0]}'),/JSON structure/);
  });
  console.log(JSON.stringify({status:'passed',checks:checks.length,oracleSystems,checksPassed:checks},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
