---
title: 月刊
layout: single
permalink: /monthly/
author_profile: true
classes: wide
---

{% assign monthly_items = site.monthly | sort: "date" | reverse %}

这里收录每个月的阶段性总结。你可以把它理解成一个独立专栏：不追求写成长文，更适合记录当月最值得留下来的技术观察、阅读笔记、项目进展和下一步计划。

## 往期月刊

<div class="feature__wrapper">
  {% for issue in monthly_items %}
    <div class="feature__item">
      <div class="archive__item">
        <h2 class="archive__item-title no_toc">
          <a href="{{ issue.url | relative_url }}">{{ issue.title }}</a>
        </h2>
        <p class="page__meta">
          <i class="far fa-calendar-alt" aria-hidden="true"></i>
          <time datetime="{{ issue.date | date_to_xmlschema }}">{{ issue.date | date: "%Y-%m-%d" }}</time>
        </p>
        {% if issue.excerpt %}
          <p class="archive__item-excerpt">{{ issue.excerpt | strip_html | strip_newlines }}</p>
        {% endif %}
        <p>
          <a href="{{ issue.url | relative_url }}" class="btn btn--primary">查看本期</a>
        </p>
      </div>
    </div>
  {% endfor %}
</div>
