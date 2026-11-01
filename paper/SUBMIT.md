# Submitting to arXiv

Nothing has been submitted. These are the steps for Abhay to do himself.

1. Build: from the repo root, `python3 paper/make_tables.py && cd paper && tectonic main.tex`.
2. Before submitting, fill in the bibliography: the six `\bibitem`s list only names and links. Add authors and titles from each paper's own page. Add the repository URL if the repo is public.
3. Make the source bundle (arXiv compiles with pdflatex; tectonic uses XeTeX, but main.tex uses only standard packages and no fontspec, and line 1 sets `\pdfoutput=1` outside XeTeX):
   `cd paper && tar czf arxiv.tar.gz main.tex tables.tex figures/hero.png`
   No .bib or .bbl is needed (inline thebibliography). pdflatex was not available on this machine, so the pdflatex build itself is unverified; arXiv shows the compiled PDF before you confirm.
4. On arxiv.org: Submit, license of your choice, primary category cs.SE, cross-list cs.AI. Upload arxiv.tar.gz, check the processed PDF, enter title and abstract from main.tex (plain text, no macros: copy the numbers from the PDF).
5. First-time submitters in cs.SE may need an endorsement.
