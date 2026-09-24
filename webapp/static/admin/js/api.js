const tg = window.Telegram?.WebApp;
export const initData = tg?.initData || '';
export const headers = {'X-Init-Data': initData, 'Content-Type':'application/json'};
export async function api(path, options={}){
  const response = await fetch(path, {credentials:'same-origin', ...options, headers:{...headers,...(options.headers||{})}});
  const text = await response.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = {error:text}; }
  if(!response.ok){ throw new Error(data.error || data.message || text || `HTTP ${response.status}`); }
  return data;
}
export const get=(path)=>api(path);
export const post=(path, body)=>api(path,{method:'POST',body:JSON.stringify(body)});
