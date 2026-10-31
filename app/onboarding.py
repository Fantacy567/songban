"""Guest entry and private starting preferences, using the existing account token."""
import json
import secrets
from typing import Literal

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA = """
CREATE TABLE IF NOT EXISTS core_guest_people (
 user_id TEXT PRIMARY KEY REFERENCES people(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS core_starting_preferences (
 user_id TEXT PRIMARY KEY REFERENCES people(id), body TEXT NOT NULL,
 revision INTEGER NOT NULL, updated_at TEXT NOT NULL
);
"""


def ensure_onboarding_schema(con):
    con.executescript(SCHEMA)


def starting_state(con, user_id):
    row = con.execute('SELECT * FROM core_starting_preferences WHERE user_id=?', (user_id,)).fetchone()
    return {
        'guest': con.execute('SELECT 1 FROM core_guest_people WHERE user_id=?', (user_id,)).fetchone() is not None,
        'preferences': {'city': '', **json.loads(row['body']), 'revision': row['revision']} if row else None,
    }


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    interests: list[Literal['宠物', '运动', '音乐', '校园生活', '画画设计', '编程', '还在探索']] = Field(min_length=1, max_length=7)
    skills: list[Literal['画画或设计', '写代码或搭网页', '整理资料', '介绍作品', '都没做过，想试试']] = Field(min_length=1, max_length=5)
    time: Literal['3小时以内', '半天', '一天', '一个周末']
    city: str = Field(default='', max_length=60)
    experience: str = Field(default='', max_length=1500)
    expected_revision: int = Field(ge=0)

    @field_validator('city')
    @classmethod
    def trim_city(cls, value):
        return value.strip()

    @model_validator(mode='after')
    def validate_choices(self):
        if len(set(self.interests)) != len(self.interests) or len(set(self.skills)) != len(self.skills):
            raise ValueError('选项不能重复。')
        if '都没做过，想试试' in self.skills and len(self.skills) > 1:
            raise ValueError('请选择做过的事情，或选择还没有做过。')
        self.experience = self.experience.strip()
        return self


def register_onboarding(api, db, problem, now, uid, digest, core):
    @api.post('/api/core/guest-session', status_code=201)
    def guest_session():
        user_id, token, created = uid(), secrets.token_urlsafe(32), now()
        with db(True) as con:
            con.execute(
                'INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,phone_real) VALUES(?,?,?,?,?,?,?,?)',
                (user_id, 'guest:' + user_id, '访客', '访客体验', '', digest(token), created, 0),
            )
            con.execute('INSERT INTO core_guest_people(user_id,created_at) VALUES(?,?)', (user_id, created))
        return {'token': token, 'guest': True}

    @api.put('/api/core/me/preferences')
    def save_preferences(body: Preferences, authorization: str = Header(default='')):
        with db(True) as con:
            user = core['person'](con, authorization)
            previous = starting_state(con, user['id'])['preferences']
            revision = previous['revision'] if previous else 0
            if body.expected_revision != revision:
                raise problem(409, 'preferences_conflict', '兴趣资料已在另一窗口更新，请读取最新选择后再保存。')
            value = body.model_dump(exclude={'expected_revision'})
            # Older clients do not send city; retain an existing choice unless
            # the caller explicitly submits an empty city to clear it.
            if 'city' not in body.model_fields_set and previous:
                value['city'] = previous.get('city', '')
            con.execute(
                'INSERT INTO core_starting_preferences(user_id,body,revision,updated_at) VALUES(?,?,?,?) '
                'ON CONFLICT(user_id) DO UPDATE SET body=excluded.body,revision=excluded.revision,updated_at=excluded.updated_at',
                (user['id'], json.dumps(value, ensure_ascii=False), revision + 1, now()),
            )
        return {'preferences': {**value, 'revision': revision + 1}}
