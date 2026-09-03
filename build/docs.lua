-- Pandoc Lua filter for the ChordCut HTML documentation (used by build/build.bat
-- together with build/docs.html and build/docs.css).
--
-- The README files are written for GitHub, where the page has no chrome of its
-- own: the first line is the download link and the first heading is the title.
-- This filter lifts both out of the body so the template can place them in the
-- banner, turns implicit figures back into plain images with alt text, marks
-- table header cells with a scope, and provides the localized labels used by
-- the template (skip link, table of contents heading, page title suffix).

-- Labels the page adds around the README text, by language code. Everything
-- else on the page comes from the README itself. To support a new language,
-- add an entry here; languages without one fall back to English.
--   doc    suffix of the browser window title ("ChordCut — Documentation")
--   toc    heading of the table of contents in the banner
--   skip   text of the skip link at the top of the page
--   copy   label of the copy button on code blocks
--   copied confirmation shown (and announced) after copying
local strings = {
  en = {
    doc = "Documentation",
    toc = "Contents",
    skip = "Skip to main content",
    copy = "Copy",
    copied = "Copied",
  },
  ru = {
    doc = "Документация",
    toc = "Содержание",
    skip = "Перейти к основному содержимому",
    copy = "Копировать",
    copied = "Скопировано",
  },
}

-- Returns the Link if the block is a paragraph holding nothing but one link.
local function sole_link(block)
  if block.t ~= "Para" then
    return nil
  end
  local link = nil
  for _, inline in ipairs(block.content) do
    if inline.t == "Link" then
      if link then
        return nil
      end
      link = inline
    elseif inline.t ~= "Space" and inline.t ~= "SoftBreak" then
      return nil
    end
  end
  return link
end

-- Screenshots are plain images described by their alt text, not captioned
-- figures: pandoc's implicit figure would repeat the alt text as a visible
-- caption under every image.
function Figure(fig)
  local inlines = pandoc.List()
  for _, block in ipairs(fig.content) do
    if block.t == "Plain" or block.t == "Para" then
      inlines:extend(block.content)
    end
  end
  return pandoc.Para(inlines)
end

-- Give header cells an explicit column scope so screen readers associate
-- them with the cells below without guessing.
function Table(tbl)
  for _, row in ipairs(tbl.head.rows) do
    for _, cell in ipairs(row.cells) do
      cell.attr.attributes.scope = "col"
    end
  end
  return tbl
end

function Pandoc(doc)
  local meta = doc.meta
  local blocks = doc.blocks
  local lang = meta.lang and pandoc.utils.stringify(meta.lang) or "en"
  local s = strings[lang:sub(1, 2)] or strings.en

  -- The leading "Download latest version" paragraph becomes the banner button.
  local link = blocks[1] and sole_link(blocks[1])
  if link then
    meta["download-url"] = pandoc.MetaString(link.target)
    meta["download-text"] = pandoc.MetaInlines(link.content)
    table.remove(blocks, 1)
  end

  -- The first level-1 heading becomes the page title shown in the banner;
  -- leaving it in the body would give the page two H1s.
  for i, block in ipairs(blocks) do
    if block.t == "Header" and block.level == 1 then
      meta.title = pandoc.MetaInlines(block.content)
      meta.pagetitle = pandoc.MetaString(
        pandoc.utils.stringify(block.content) .. " — " .. s.doc
      )
      table.remove(blocks, i)
      break
    end
  end

  -- Give each caption-less table a <caption> repeating the heading that
  -- introduces it, so screen readers announce "Keyboard Shortcuts table" when
  -- jumping between tables. The caption is visually hidden by the stylesheet
  -- because the heading is already on screen right above the table.
  local heading = nil
  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      heading = block.content
    elseif block.t == "Table" and heading then
      if #pandoc.utils.stringify(block.caption.long) == 0 then
        block.caption.long = pandoc.Blocks({ pandoc.Plain(heading) })
      end
    end
  end

  meta["toc-title"] = pandoc.MetaString(s.toc)
  meta["skip-label"] = pandoc.MetaString(s.skip)
  meta["copy-label"] = pandoc.MetaString(s.copy)
  meta["copied-label"] = pandoc.MetaString(s.copied)
  return pandoc.Pandoc(blocks, meta)
end
