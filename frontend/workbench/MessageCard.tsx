import { SpecialistAvatar } from './SpecialistAvatar';
import { dateText } from './songban-adapter';
import { allowedPages, roles, sourceNature, type Action, type Message, type Source } from './types';

export function Sources({ sources }: { sources: Source[] }) {
  return sources.length ? <ul className="sbw-sourceList">{sources.map((source, index) => <li key={`${source.id}:${index}`}><span>{source.name || source.id}</span>{source.version != null && <small>v{source.version}</small>}{source.nature && <small>{sourceNature(source.nature)}</small>}{source.truncated && <small>已截断，未完整读取</small>}{source.status === 'partial' && <small>部分解析，请核对原文</small>}{source.warnings?.map((warning, i) => <p className="sbw-muted" key={i}>{typeof warning === 'string' ? warning : warning && typeof warning === 'object' && 'message' in warning && typeof warning.message === 'string' ? warning.message : '此来源存在解析提示，请在材料页核对。'}</p>)}</li>)}</ul> : <p className="sbw-muted">本轮未选择材料，回答依据本人对话和可访问的团队事实。</p>;
}
// Message row/bubble/cardHead from AiWorkbench; metadata and sources from TeamAssistantPanel.
export function MessageCard({ message, canPrepare, canReview, onAction, onShare }: {
  message: Message; canPrepare: boolean; canReview: boolean;
  onAction(action: Action): void; onShare(): void;
}) {
  const assistant = message.role === 'assistant';
  const role = roles.find(item => item.id === message.role_id);
  const actions = (message.actions || []).filter(action =>
    action.type === 'open_page' && allowedPages.has(action.page || '') || action.type === 'prepare_direction' && canPrepare || action.type === 'request_team_review' && canReview);
  return <div className={assistant ? 'sbw-aiRow' : 'sbw-userRow'}><article className={assistant ? 'sbw-aiBubble' : 'sbw-userBubble'}>
    <div className="sbw-cardHead">{assistant && <SpecialistAvatar specialistKey={message.role_id} size={24} />}<strong>{assistant ? role?.name || '项目助手' : '我'}</strong><time dateTime={message.created_at}>{dateText(message.created_at)}</time></div>
    <p className="sbw-messageText">{message.text}</p>
    {assistant && <><details className="sbw-details"><summary>本轮来源与模型{message.mode === 'fixture' ? ' · 模拟测试' : ''}</summary><Sources sources={message.sources || []} />{message.coverage?.history_limited && <p className="sbw-muted">本轮只采用部分历史。</p>}<p className="sbw-muted">实际模型：{message.actual_model || '未知'}{message.requested_model ? `；请求配置：${message.requested_model}` : ''}。{message.mode === 'fixture' && '此回答来自测试夹具，不能代表真实模型效果。'}</p></details><div className="sbw-actions">{actions.map((action, index) => <button type="button" key={index} onClick={() => onAction(action)}>{action.label || (action.type === 'prepare_direction' ? '核对方向草稿' : action.type === 'request_team_review' ? '进入团队统筹' : '查看相关页面')}</button>)}<button type="button" className="sbw-textButton" onClick={onShare}>选择内容共享</button></div></>}
  </article></div>;
}
