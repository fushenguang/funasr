import defaultMdxComponents from 'fumadocs-ui/mdx';
import { Mermaid } from 'fumadocs-mermaid/ui';
import type { MDXComponents } from 'mdx/types';

function Img(props: React.ImgHTMLAttributes<HTMLImageElement>) {
  // fumadocs-mdx imports images as objects with .src, .width, .height
  // unwrap to get the actual URL string for native <img>
  const src =
    typeof props.src === 'object' && props.src !== null && 'src' in props.src
      ? String((props.src as { src: unknown }).src)
      : props.src;

  // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
  return <img {...props} src={src as string} loading="eager" />;
}

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    Mermaid,
    img: Img,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
