
:root{
  --et-red:#e11414;
  --et-red-dark:#b90e0e;
  --et-bg:#f3f4f6;
  --et-card:#ffffff;
  --et-text:#111827;
  --et-muted:#6b7280;
  --et-border:#e5e7eb;
}
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Arial, Helvetica, sans-serif;
  background:var(--et-bg);
  color:var(--et-text);
}
.page-shell{
  max-width:1100px;
  margin:0 auto;
  padding:24px;
}
.topbar{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:16px;
  margin-bottom:18px;
}
.page-title{
  display:flex;
  align-items:center;
  gap:10px;
  font-size:32px;
  font-weight:800;
  margin:0;
}
.subtitle{
  color:var(--et-muted);
  margin:0 0 20px;
  font-size:16px;
}
.card{
  background:var(--et-card);
  border:1px solid var(--et-border);
  border-radius:18px;
  padding:20px;
  box-shadow:0 4px 14px rgba(0,0,0,.05);
}
.actions{
  display:flex;
  flex-wrap:wrap;
  gap:12px;
  margin-top:18px;
}
.btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:44px;
  padding:0 16px;
  border:none;
  border-radius:12px;
  font-weight:700;
  text-decoration:none;
  cursor:pointer;
}
.btn-primary{
  background:var(--et-red);
  color:white;
}
.btn-primary:hover{background:var(--et-red-dark)}
.btn-secondary{
  background:#fff;
  color:var(--et-text);
  border:1px solid var(--et-border);
}
.placeholder-box{
  margin-top:20px;
  padding:16px;
  border-radius:14px;
  background:#fafafa;
  border:1px dashed #d1d5db;
}
.kv{
  display:grid;
  grid-template-columns:180px 1fr;
  gap:10px;
  margin-top:12px;
}
.kv div:nth-child(odd){
  font-weight:700;
}
