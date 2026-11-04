import fs from 'node:fs/promises';
import {build} from 'esbuild';
const result=await build({entryPoints:['app.tsx'],bundle:true,write:false,minify:true,format:'iife',target:'es2020',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'},legalComments:'inline'});
const research=JSON.parse(await fs.readFile('research.json','utf8'));
const css=(await fs.readFile('styles.css','utf8'))+'\n'+await fs.readFile('unified.css','utf8');
const html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TRADERS OS — Connected Ecosystem</title><style>'+css+'</style></head><body><div id="root"></div><script>window.RESEARCH='+JSON.stringify(research).replace(/</g,'\\u003c')+';</script><script>'+result.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')+'</script></body></html>';
await fs.writeFile('traders-os-unified.html',html);
