import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { to: "/", label: "检索" },
  { to: "/import", label: "导入" },
  { to: "/tasks", label: "任务" },
  { to: "/keywords", label: "词库" }
];

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <p className="eyebrow">内部排查</p>
          <h1>视频画面检索</h1>
          <p className="subtitle">将无语音录屏视频转成可检索证据，快速定位可疑操作与时间点。</p>
        </div>
        <nav className="nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
