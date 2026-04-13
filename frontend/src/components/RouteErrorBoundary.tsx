import { Link, useRouteError } from "react-router-dom";

export function RouteErrorBoundary() {
  const error = useRouteError();
  const message = error instanceof Error ? error.message : "页面渲染失败，请刷新后重试。";

  return (
    <section className="panel-grid">
      <div className="panel panel-wide">
        <p className="eyebrow">页面异常</p>
        <h2>当前页面未能正常加载</h2>
        <p>{message}</p>
        <div className="action-row">
          <Link to="/" className="button-link">
            返回检索页
          </Link>
        </div>
      </div>
    </section>
  );
}
