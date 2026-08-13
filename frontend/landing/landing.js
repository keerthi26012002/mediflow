/*
 * MediFlow AI — Public Landing Page JavaScript
 * Adapted from TemplateMo 618 "The Catalyst"
 * Isolated from Dashboard state, API, JWT, and WebSocket operations
 */

(function() {
    'use strict';

    /* ===== Theme Controller (Syncs with MediFlow mediflow-theme) ===== */
    function getStoredTheme() {
        try {
            const saved = localStorage.getItem('mediflow-theme');
            if (saved === 'light' || saved === 'dark') return saved;
        } catch (e) {
            console.warn('Unable to access localStorage for theme:', e);
        }
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }

    function applyTheme(theme, save = true) {
        document.documentElement.setAttribute('data-theme', theme);
        if (save) {
            try {
                localStorage.setItem('mediflow-theme', theme);
            } catch (e) {
                console.warn('Unable to save theme preference:', e);
            }
        }

        const isDark = theme === 'dark';
        const icon = isDark ? '🌙' : '☀️';
        const label = isDark ? 'Dark' : 'Light';
        const title = isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode';

        document.querySelectorAll('.btn-theme-toggle').forEach(btn => {
            const iconEl = btn.querySelector('.theme-icon');
            const textEl = btn.querySelector('.theme-text');
            if (iconEl) iconEl.textContent = icon;
            if (textEl) textEl.textContent = label;
            btn.title = title;
            btn.setAttribute('aria-label', title);
        });
    }

    window.toggleLandingTheme = function() {
        const current = document.documentElement.getAttribute('data-theme') || getStoredTheme();
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next, true);
    };

    // System OS theme changes
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            try {
                if (!localStorage.getItem('mediflow-theme')) {
                    applyTheme(e.matches ? 'dark' : 'light', false);
                }
            } catch (err) {}
        });
    }

    /* ===== Mobile Navigation Toggle ===== */
    function initNav() {
        const navToggle = document.getElementById('navToggle');
        const navLinks  = document.getElementById('navLinks');
        if (!navToggle || !navLinks) return;

        navToggle.addEventListener('click', () => {
            navToggle.classList.toggle('active');
            navLinks.classList.toggle('open');
            document.body.style.overflow = navLinks.classList.contains('open') ? 'hidden' : '';
            navToggle.setAttribute('aria-expanded', navToggle.classList.contains('active'));
        });

        navLinks.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navToggle.classList.remove('active');
                navLinks.classList.remove('open');
                document.body.style.overflow = '';
                navToggle.setAttribute('aria-expanded', 'false');
            });
        });
    }

    /* ===== FAQ Accordion ===== */
    function initFaq() {
        function faqOpen(item) {
            const answer = item.querySelector('.faq-answer');
            if (!answer) return;
            item.classList.add('open');
            answer.style.maxHeight = answer.scrollHeight + 'px';
            const q = item.querySelector('.faq-question');
            if (q) q.setAttribute('aria-expanded', 'true');
        }

        function faqClose(item) {
            const answer = item.querySelector('.faq-answer');
            if (!answer) return;
            item.classList.remove('open');
            answer.style.maxHeight = '0';
            const q = item.querySelector('.faq-question');
            if (q) q.setAttribute('aria-expanded', 'false');
        }

        document.querySelectorAll('.faq-question').forEach(btn => {
            btn.addEventListener('click', () => {
                const item = btn.closest('.faq-item');
                if (item.classList.contains('open')) {
                    faqClose(item);
                } else {
                    faqOpen(item);
                }
            });
        });

        const expandBtn = document.getElementById('faqExpandAll');
        if (expandBtn) {
            expandBtn.addEventListener('click', () => {
                document.querySelectorAll('.faq-item').forEach(item => faqOpen(item));
            });
        }

        const collapseBtn = document.getElementById('faqCollapseAll');
        if (collapseBtn) {
            collapseBtn.addEventListener('click', () => {
                document.querySelectorAll('.faq-item').forEach(item => faqClose(item));
            });
        }
    }

    /* ===== Scroll Reveal Animations ===== */
    function initScrollReveal() {
        const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const reveals = document.querySelectorAll('.reveal');

        if (!prefersReduced && 'IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach((entry, i) => {
                    if (entry.isIntersecting) {
                        entry.target.style.transitionDelay = `${(i % 5) * 60}ms`;
                        entry.target.classList.add('visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });

            reveals.forEach(el => observer.observe(el));

            // Fallback timeout to ensure visibility
            setTimeout(() => {
                reveals.forEach(el => el.classList.add('visible'));
            }, 2500);
        } else {
            reveals.forEach(el => el.classList.add('visible'));
        }
    }

    // Initialize on DOM load
    document.addEventListener('DOMContentLoaded', () => {
        const initialTheme = getStoredTheme();
        applyTheme(initialTheme, false);
        initNav();
        initFaq();
        initScrollReveal();
    });

})();
