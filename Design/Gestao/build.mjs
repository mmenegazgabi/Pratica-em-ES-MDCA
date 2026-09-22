import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const dir=path.dirname(fileURLToPath(import.meta.url));
const css=fs.readFileSync(path.join(dir,'style.css'),'utf8');
const js=fs.readFileSync(path.join(dir,'app.js'),'utf8');
const embedded=css.replace(/url\("assets\/([^"\n]+)"\)/g,(_,file)=>'url("data:font/ttf;base64,'+fs.readFileSync(path.join(dir,'assets',file)).toString('base64')+'")');
const html=fs.readFileSync(path.join(dir,'index.html'),'utf8')
 .replace('<link rel="stylesheet" href="style.css">',()=>'<style>'+embedded+'</style>')
 .replace('<script src="app.js"></script>',()=>'<script>'+js+'</script>');
fs.writeFileSync(path.join(dir,'MDCA_Gestao_E2.html'),html);
console.log('HTML portátil atualizado: MDCA_Gestao_E2.html');
