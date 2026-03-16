
function etParseJwt(token){
  try{
    if(!token) return null;
    const parts0 = String(token).trim().split(" ");
    const raw = (parts0.length===2 && parts0[0].toLowerCase()==="bearer") ? parts0[1] : token;
    const parts = raw.split(".");
    if(parts.length!==3) return null;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(atob(base64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join(""));
    return JSON.parse(jsonPayload);
  }catch(e){ return null; }
}
function etGetToken(){
  return (localStorage.getItem("access_token") || localStorage.getItem("token") || "").trim();
}
function etGetRoleName(){
  const direct = (localStorage.getItem("role_name") || localStorage.getItem("role") || "").trim();
  if(direct) return direct.toUpperCase();
  const payload = etParseJwt(etGetToken());
  return String(payload?.role_name || payload?.role || "").trim().toUpperCase();
}
function etGetUserName(){
  const direct = (localStorage.getItem("full_name") || localStorage.getItem("username") || "").trim();
  if(direct) return direct;
  const payload = etParseJwt(etGetToken());
  return payload?.username || "Signed in";
}
function etLogout(){
  ["access_token","token","token_type","role_name","role","username","full_name","jwt"].forEach(k => {
    try { localStorage.removeItem(k); sessionStorage.removeItem(k); } catch(e){}
  });
  window.location.href = "/static/index.html";
}
document.addEventListener("DOMContentLoaded", () => {
  const u = document.getElementById("shellUserName");
  const r = document.getElementById("shellRoleName");
  const t = document.getElementById("shellToday");
  if (u) u.textContent = etGetUserName();
  if (r) r.textContent = etGetRoleName() || "-";
  if (t) t.textContent = new Date().toLocaleString([], {year:"numeric",month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"});
  const lb = document.getElementById("logoutBtn");
  if (lb) lb.addEventListener("click", etLogout);
});
