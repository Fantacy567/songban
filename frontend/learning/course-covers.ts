/** Original repository-owned examples, never child uploads or external image URLs.
 * Copyright © 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
 */
export interface CoursePresentation {
  image: string; alt: string; goal: string; preparation: string; experience: string;
  steps: string[]; source: string; assetVersion: string;
}
const covers: Readonly<Record<string, CoursePresentation>> = {
  'invitation-course@0.1.0': {
    image: '/static/learning/covers/invitation-v1.svg',
    alt: '邀请卡作品示例：松果班故事交换会，卡片上有邀请对象、时间、地点和准备物品。',
    goal: '做一张让同学看得懂的活动邀请卡。',
    preparation: '读一张活动资料卡；松伴会在需要时给你提示。',
    experience: '没用过 AI 也可以从第一步试起。',
    steps: ['想一想：找出邀请谁、何时、在哪里', '做出来：表达要求，查看并保存作品', '改一改：亲手修改，解释你的判断'],
    source: '松伴课程模板原创示例；内容取自本课虚构材料 MAT_A@0.1.0。',
    assetVersion: 'invitation-cover@1.0.0',
  },
};
export function coursePresentation(courseVersion: string): CoursePresentation | null { return covers[courseVersion] || null; }
