require 'kramdown'
require 'nokogiri'
require 'yaml'
require 'date'
require 'cgi'

ROOT = '/Users/boyang/Documents/UGit/BiBoyang.github.io'
SOURCE = File.join(ROOT, '_posts/2026-10-26-长程-agent-先问失效再选机制.md')
OUTPUT = File.join(ROOT, '_wechat/公众号排版-2026-10-26-长程Agent先问失效再选机制.html')
RAW_IMAGE = 'https://raw.githubusercontent.com/BiBoyang/BiBoyang.github.io/refs/heads/main/Image/'
TITLE = '长程 Agent：先问失效，再选机制'
SUMMARY = '长程 Agent 的机制没有统一答案。本文用六次故障注入 pilot 和一组暴露反例，拆解自我条件化、权威排序与自检失真，并给出选择机制的四道证据：基线确有失效、机制实际启动、系统决策改变、独立结果与资源消耗成立。'

source = File.read(SOURCE)
parts = source.split(/^---\s*$/)
front_matter = YAML.safe_load(parts[1], permitted_classes: [Date, Time])
raise 'front matter mismatch' unless front_matter['title'] == TITLE && front_matter['layout'] == 'post'
body = parts[2]
fragment = Nokogiri::HTML::DocumentFragment.parse(Kramdown::Document.new(body).to_html)

P_STYLE = 'font-size:16px;color:#3f3f3f;line-height:1.9;margin:0 0 1.1em;letter-spacing:0.02em;'
H2_STYLE = 'font-size:19px;font-weight:700;color:#1f2328;line-height:1.4;margin:1.8em 0 0.9em;padding-left:10px;border-left:4px solid #2f6fdb;'
H3_STYLE = 'font-size:17px;font-weight:700;color:#1f2328;line-height:1.45;margin:1.5em 0 0.8em;'
LIST_STYLE = 'padding-left:1.3em;margin:0 0 1.1em;font-size:16px;color:#3f3f3f;line-height:1.9;'
CODE_STYLE = 'font-family:Menlo,Consolas,monospace;font-size:0.86em;background:#f3f4f6;padding:2px 5px;border-radius:4px;color:#c7254e;'
CAPTION_STYLE = 'font-size:13px;color:#8a8f98;line-height:1.7;margin:0 0 1.2em;'

fragment.css('p').each { |node| node['style'] = P_STYLE }
fragment.css('h2').each { |node| node['style'] = H2_STYLE }
fragment.css('h3').each { |node| node['style'] = H3_STYLE }
fragment.css('ul, ol').each { |node| node['style'] = LIST_STYLE }
fragment.css('li').each { |node| node['style'] = 'margin-bottom:0.35em;' }
fragment.css('strong').each { |node| node['style'] = 'color:#111;' }
fragment.css('code').each { |node| node['style'] = CODE_STYLE }
fragment.css('a').each { |node| node['style'] = 'color:#2f6fdb;text-decoration:none;' }
fragment.css('table').each { |node| node['style'] = 'border-collapse:collapse;width:100%;margin:1.2em 0;font-size:14px;' }
fragment.css('th').each { |node| node['style'] = 'background:#f3f6fb;border:1px solid #dfe3e8;padding:8px 10px;color:#1f2328;font-weight:700;text-align:left;' }
fragment.css('td').each { |node| node['style'] = 'border:1px solid #dfe3e8;padding:8px 10px;color:#3f3f3f;' }
fragment.css('blockquote').each do |node|
  node['style'] = 'background:#f3f6fb;border-left:4px solid #2f6fdb;border-radius:0 6px 6px 0;padding:12px 16px;margin:1.2em 0;font-size:16px;color:#1f2328;line-height:1.9;'
  node.css('p').each { |p| p['style'] = 'margin:0;' }
end
fragment.css('pre').each { |node| node['style'] = 'display:block;overflow-x:auto;padding:16px;background:#18324b;color:#f7f8fa;border-radius:8px;font-size:14px;line-height:1.65;margin:1.2em 0;' }
fragment.css('pre code').each { |node| node['style'] = 'font-family:Menlo,Consolas,monospace;background:transparent;padding:0;color:inherit;font-size:14px;line-height:1.65;' }
fragment.css('hr').each { |node| node['style'] = 'border:none;border-top:1px solid #e5e7eb;margin:2em 0;' }
fragment.css('img').each do |node|
  node['style'] = 'max-width:100%;height:auto;margin:0.6em 0 0.2em;border-radius:8px;display:block;'
  node['src'] = node['src'].sub(%r{^/Image/}, RAW_IMAGE)
end
fragment.css('p > em').each do |em|
  next unless em.text.strip.start_with?('图 ')
  parent = em.parent
  parent['style'] = CAPTION_STYLE
  em['style'] = 'font-style:normal;'
end

notes = <<~HTML
<section style="border:2px dashed #d93025;border-radius:8px;padding:14px 16px;margin:0 0 24px;font-size:14px;color:#57606a;line-height:1.8;background:#fffaf5;">
<p style="margin:0 0 6px;font-weight:700;color:#d93025;">【发布前请删除此框】公众号填写建议</p>
<p style="margin:0 0 4px;"><b>标题</b>：#{CGI.escapeHTML(TITLE)}</p>
<p style="margin:0 0 4px;"><b>摘要</b>：#{CGI.escapeHTML(SUMMARY)}</p>
<p style="margin:0 0 4px;"><b>封面</b>：可用 <code style="font-family:Menlo,Consolas,monospace;">Image/GoalMechanism_EvidenceGates.png</code>（16:9）；需要 2.35:1 标准封面时，可基于该图裁切。</p>
<p style="margin:0 0 4px;"><b>合集</b>：自行选择 AI / Agent 相关合集。</p>
<p style="margin:0;"><b>使用方式</b>：浏览器打开本文件 → 从“零、前言”开始全选正文（<b>不选本提示框</b>）→ 复制渲染后的富文本并粘贴进公众号编辑器。三张内嵌图使用 GitHub 图床，需在图片文件推送到 main 后确认编辑器已抓取上传；若未抓取，用图片工具按原链接手动补传。</p>
</section>
HTML

footer = <<~HTML
<hr style="border:none;border-top:1px solid #e5e7eb;margin:2em 0;" />
<p style="font-size:13px;color:#8a8f98;line-height:1.8;margin:0 0 1.1em;">注：本文同步发布于个人博客 biboyang.github.io。</p>
HTML

html = <<~HTML
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>公众号排版预览 - #{CGI.escapeHTML(TITLE)}</title>
</head>
<body style="margin:0;padding:24px;background:#ffffff;">
<section style="max-width:677px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">

#{notes}
#{fragment.to_html}
#{footer}
</section>
</body>
</html>
HTML

Dir.mkdir(File.dirname(OUTPUT)) unless Dir.exist?(File.dirname(OUTPUT))
File.write(OUTPUT, html)
puts OUTPUT
